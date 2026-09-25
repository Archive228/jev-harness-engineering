# Codex: interview, planning, and the transition into execution

Inspected on 2026-09-21. Official source: [openai/codex](https://github.com/openai/codex), pinned to [`d99213289f9abe6daeefa50cde67634d9ea6eeed`](https://github.com/openai/codex/commit/d99213289f9abe6daeefa50cde67634d9ea6eeed), commit dated 2026-09-20. This is a source inspection of the relevant planning, question, protocol, rendering, and test paths, not a claim to have read every file in Codex or to have run its Rust test suite.

## Main finding

The useful feature to borrow is a separate conversation stage: discover facts → settle the person's intent → prepare a concrete plan → let the person start implementation. A nice input box alone does not supply this behaviour. The official [best-practices guide](https://learn.chatgpt.com/guides/best-practices#plan-first-for-difficult-tasks) explicitly recommends planning or an interview for vague ideas and organising the task around outcome, context, constraints, and completion criteria.

This is not something Jev itself supplies. In our architecture the conversational model prepares the task; Jev scores typed choices during execution. An interview is therefore a host/model workflow before the Jev execution loop, not a new free-text Jev API.

## 1. What the upstream plan prompt actually does

[`plan.md:41–58`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/collaboration-mode-templates/templates/plan.md#L41-L58) defines three phases:

1. Inspect the actual environment. Resolve facts from files before asking the user.
2. Settle intent: goal, success, audience, scope, constraints, current state, preferences, and tradeoffs.
3. Settle implementation: approach, interfaces, data flow, failure cases, tests, and relevant compatibility constraints.

The distinction between discoverable facts and preferences is explicit in [`plan.md:77–90`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/collaboration-mode-templates/templates/plan.md#L77-L90). A repository can answer “what language does this use?”; it cannot answer “do I want a report or a runnable tool?” Asking both questions indiscriminately makes an interview feel bureaucratic.

Planning permits inspection and some non-mutating validation, but prohibits implementing tracked-file changes. This is a collaboration-mode instruction, distinct from the progress/checklist tool: [`plan.md:5–39`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/collaboration-mode-templates/templates/plan.md#L5-L39).

Final plans are delimited with `<proposed_plan>` tags for special client rendering. The prompt asks for a clear title, summary, interface changes where relevant, tests, and explicit assumptions. Later instructions deliberately discourage unnecessary detail, speculative schemas, and file-by-file inventories. A revision must be a complete replacement rather than an ambiguous patch to an old plan: [`plan.md:92–128`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/collaboration-mode-templates/templates/plan.md#L92-L128).

Our adaptation keeps that sequence but returns a schema-validated JSON object, because our Textual client can render a plan directly without parsing XML-like tags. It also constrains the scope to one coherent small deliverable and targets one or two rounds of questions. Those limits are our product choices, not claims about upstream behaviour.

## 2. Question contract: instructions versus actual validation

The model-facing tool definition is in [`request_user_input_spec.rs:16–88`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/core/src/tools/handlers/request_user_input_spec.rs#L16-L88). Its shape is:

```json
{
  "questions": [{
    "id": "result_format",
    "header": "Result",
    "question": "What should you receive at the end?",
    "options": [
      {"label": "Local CLI (Recommended)", "description": "A runnable tool with an example input."},
      {"label": "Written report", "description": "A comparison and findings without building a program."}
    ]
  }]
}
```

The descriptions request one to three questions, preferably one; a short header of at most 12 characters; two to three mutually exclusive options; short labels; and the recommended choice first. The client adds the custom-answer route.

These are **not all hard validators** in this pinned upstream implementation. The tool uses `strict: false`; the array constraints and length limits are prose descriptions. The normaliser checks that every question has nonempty options and then forces `isOther=true`: [`request_user_input_spec.rs:105–120`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/core/src/tools/handlers/request_user_input_spec.rs#L105-L120). It does not enforce unique IDs, three-question maximum, two-to-three option count, or the header length. One normalisation test even deliberately uses one option: [`request_user_input_spec_tests.rs:111–155`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/core/src/tools/handlers/request_user_input_spec_tests.rs#L111-L155).

For our app, enforce limits in Python after model output is decoded. Reject malformed or duplicate IDs, missing options, empty text, and unsupported response kinds; do not silently start execution with a partial model response. Keep rendering text literal so option labels cannot create Rich markup or terminal control effects.

The broader protocol type permits optional options and includes `isOther` and `isSecret`; it can represent forms beyond the narrower model-facing tool. Responses are keyed by stable question ID, not by the displayed index:

```json
{
  "answers": {
    "result_format": {
      "answers": ["Local CLI (Recommended)", "user_note: I want to run it without an API key."]
    }
  }
}
```

See [`protocol/src/request_user_input.rs:8–52`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/protocol/src/request_user_input.rs#L8-L52) and the concrete response builder in [`mod.rs:841–889`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L841-L889).

## 3. The question UI is a state machine

Codex keeps one answer state per question: selected option, notes draft, explicit commitment, and whether notes are visible. Drafts include pending paste contents, not merely the displayed paste placeholder. The question overlay reuses the main composer with slash commands and attachment behaviour disabled: [`mod.rs:102–159`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L102-L159), [`mod.rs:182–202`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L182-L202).

Useful details:

- **Highlight is not an answer.** The first option starts highlighted while `answer_committed` remains false. Enter or a number commits it; merely moving the cursor or opening the form does not authorise anything. [`mod.rs:676–705`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L676-L705), [`mod.rs:1288–1349`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L1288-L1349).
- **Back preserves the question draft.** Question navigation saves the current draft, changes index, and restores the next draft. PgUp/PgDn and Ctrl+P/Ctrl+N are available across focus modes. [`mod.rs:743–763`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L743-L763), [`mod.rs:1217–1244`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L1217-L1244).
- **Custom answer is first class.** The UI appends “None of the above” for `isOther`. Enter on it opens notes. An option can also carry notes. [`mod.rs:708–740`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L708-L740), [`mod.rs:1323–1334`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L1323-L1334).
- **Paste does not submit.** Pasting switches to notes, clears commitment, and sends the text through the shared composer. Tests cover large paste surviving question switches and submission/back navigation. [`mod.rs:1453–1466`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L1453-L1466), [`mod.rs:3288–3344`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L3288-L3344).
- **Skipping is explicit.** Moving to a later question does not commit an answer. Finishing with unanswered questions opens a Proceed/Go back screen. Unanswered entries serialise as empty arrays; the recommended answer is not invented. [`mod.rs:827–874`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L827-L874), [`mod.rs:961–1019`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L961-L1019).
- **Cancellation is not completion.** Interrupt sends an interrupt event and closes the overlay. The source explicitly notes that reliable persistence of partially committed interrupted answers is unfinished upstream. [`mod.rs:1195–1200`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L1195-L1200), [`mod.rs:1428–1446`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L1428-L1446).

Do not copy every key behaviour blindly. In this revision Escape or Tab from option notes **clears the notes**. Ordinary typing while the option list has focus also does not automatically open notes, despite an outdated module comment claiming otherwise; a test explicitly checks this. These are poor defaults for the requested friendly intake, where drafts should survive dismissal and users should be able to type their own answer immediately. See [`mod.rs:802–816`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L802-L816), [`mod.rs:2322–2341`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L2322-L2341).

## 4. Why the interface remains understandable

The visible form focuses on a progress line, the current question, options, optional notes, and contextual key hints. It is not mixed with the execution log. Responsive layout measures wrapped option rows, reserves room for progress and hints, and only allocates notes space when notes are open: [`layout.rs:17–195`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/layout.rs#L17-L195).

Completed exchanges become compact history entries: how many questions were answered, the questions, selected answers, and notes. Secret answers are masked in both display and raw text. [`history_cell/request_user_input.rs:14–176`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/history_cell/request_user_input.rs#L14-L176). Our task questionnaire should not request secrets at all.

For Jev's terminal this suggests a single active interview surface above the composer, visible Back/Next/custom-answer actions, and a compact completed summary in chat. The request, questions, plan, and execution should have distinct states. Keep raw tool output under the existing expandable execution group rather than displaying planning form events as worker logs.

## 5. Plan review is a real transition, not a decorative message

[`plan_implementation.rs:9–113`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/chatwidget/plan_implementation.rs#L9-L113) presents three choices: implement, implement in a fresh context, or continue planning. The first sends a new user message with the Default collaboration mode. The second embeds the complete plan in a fresh context. The third dismisses the picker without dispatching implementation.

This provides a reusable invariant: **a displayed plan does not itself call the worker**. The host performs a deliberate transition after the user's action. Our equivalent can be simpler: Run this plan / Change it / Back to chat. The accepted plan must be retained as the exact execution input, along with the original request and answers; a future model must not silently replace it while execution starts.

Upstream tests check that the implementation prompt appears only for a completed proposed plan, is not reopened by replay, is shown only once, and is suppressed when a later user steer invalidates the plan: [`tests/plan_mode.rs:820–1088`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/chatwidget/tests/plan_mode.rs#L820-L1088). These are useful tests for our session-resume and stale-button behaviour too.

## 6. Version-sensitive protocol detail

The [official App Server documentation](https://learn.chatgpt.com/docs/app-server#toolrequestuserinput) describes server-initiated questions and `serverRequest/resolved` cleanup when an answer arrives or a turn ends/interruption removes the request. The pinned source has advanced beyond the timeout wording in that page: `autoResolutionMs` is deprecated, and `isBlocking` determines whether the question blocks. Plan mode sets `isBlocking=true` and no timeout: [`request_user_input.rs:75–96`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/core/src/tools/handlers/request_user_input.rs#L75-L96), [`protocol/src/request_user_input.rs:31–41`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/protocol/src/request_user_input.rs#L31-L41).

The TUI uses a fixed 60-second hidden grace plus 60-second visible countdown for nonblocking questions; any interaction snoozes auto-resolution. Blocking questions never auto-resolve: [`mod.rs:263–309`](https://github.com/openai/codex/blob/d99213289f9abe6daeefa50cde67634d9ea6eeed/codex-rs/tui/src/bottom_pane/request_user_input/mod.rs#L263-L309). Our plan review should wait for a real action. A timer must not count as agreement to implement.

## 7. What we actually copied and adapted

Exact upstream files are retained under `terminal-agent/vendor/codex/`:

- `plan.md`: the complete upstream planning template.
- `request_user_input_spec.rs`: the complete model-facing schema and normalisation implementation.
- `ToolRequestUserInputParams.json` and `ToolRequestUserInputResponse.json`: generated protocol contracts.
- Original `LICENSE` and `NOTICE`, plus `source.json` with original paths, commit, permanent URLs, and SHA-256 values.

The Apache-2.0 license permits source reuse under its conditions; the copies retain notices and licensing. The modified resource is clearly labelled: `jev_agent/prompts/intake.md`, with an adaptation record in `vendor/codex/ADAPTATIONS.md`. It carries the researched planning sequence into our actual runtime prompt. We did not copy or compile the whole Rust TUI, and we do not claim that a Python Textual form is the Codex UI.

The product prompt adds bounded context-only inspection, one coherent deliverable, a small interview, schema output instead of plan tags, explicit acceptance, no credentials, and host-controlled execution. These are documented changes, not disguised upstream features.

## Verification priorities for the adaptation

Meaningful tests should exercise the boundaries: malformed response rejection; unique question IDs; a custom multiline answer; back-navigation preserving drafts; explicit skip represented as unknown; cancel without execution; no worker calls while asking or planning; plan edits invalidating previous approval; an approval launching exactly once with the exact accepted plan; resumed pending questions/plan remaining actionable; a completed historical plan not relaunching; and narrow terminal layout preserving the primary action.

For a live demonstration, use a vague request such as “Хочу что-то полезное про крипту” (“I want something useful about crypto”), choose a specific outcome, then inspect the generated plan before running. That exact phrasing is the `ROUGH_REQUEST` fixture in `tests/test_guided_tui.py`, so it is quoted as recorded rather than translated. The live run was conducted in Russian as well: its own request, questions and plans are saved in Russian under `verification/guided/`, while the README and the test output in that folder are in English. The evidence must distinguish the real planning model response, the user's answers, the accepted plan, the subsequent Jev choices, and the actual checks. A recorded questionnaire with fixed canned answers is useful for UI testing but is not evidence of live model quality.
