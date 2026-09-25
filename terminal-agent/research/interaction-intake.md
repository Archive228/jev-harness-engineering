# From a vague request to a usable Jev task

Research date: 21 September 2026. This is a targeted audit of interaction paths,
not a claim to have read or tested every line of another agent. The starting Jev
screen is the saved `terminal-pink-result-browser.png`; production code references
below describe the version before the intake redesign. That screen is from a
Russian-language run, so its interface strings are quoted as recorded with an
English gloss in parentheses; the Russian example request below is quoted from
the `ROUGH_REQUEST` fixture in `tests/test_guided_tui.py`. The linked upstream
sources, the method notes and test output under `verification/guided/`, and the
current `jev_agent/` interface strings are English.

## What is wrong with the existing interaction

The pink palette is coherent. The main problem is the distribution of attention
and the absence of an explicit requirements stage.

1. **Execution begins before the product knows what “done” means.** In
   `core.py`, `_execute` asks Jev for a route, retrieves context and calls the
   worker. The worker is told to ask a concise question only if essential
   information is missing. There is no structured question request, answer
   collection, task brief or reviewed plan. A low-confidence route becomes a
   read-only turn, but uncertainty is not the same as an interview. A review can
   return `needs_input` after work has already happened; it still carries ordinary
   worker prose, not an actionable question card.
2. **The interface duplicates state.** The masthead displays both `ОЖИДАНИЕ`
   (“WAITING”) and the preceding success. The phase strip, activity title, result
   row and status counters repeat that run. The saved capture is 126×48, and the header,
   navigation, phase strip, result row, status counters and composer furniture
   take a good half of those rows before any conversation is shown.
3. **Several controls have equal visual priority.** Navigation, result actions,
   execution mode, Jev mode, expansion and send all resemble primary buttons.
   A new user has to decode the architecture before deciding what to do next.
4. **The visible plan is machine-oriented.** `CHECKS → CODEX → JEV REVIEW → RESULT`
   is a useful execution trace but does not say what the user will receive. A
   user-oriented plan says “read the transactions; calculate balances; produce a
   report; verify sample cases”. Both can exist, at different levels.
5. **A passed contract is not the whole requested result.** Existing checks can
   pass while a new output requirement remains unverified. The backend already
   records this distinction; the interface should show the task deliverables and
   actual checks together, without turning proposed checks into green successes.

These are findings about our screen and code, not an unsupported claim that
another product is always more usable.

## What the official Claude material establishes

Anthropic describes three elicitation attempts: combining questions with the
plan caused ambiguity; parsing specially formatted Markdown was unreliable; a
dedicated structured question tool worked better and paused the loop until an
answer. The lesson for this project is to keep requirements collection and plan
acceptance as separate states. We have not obtained or copied Claude Code's
closed terminal implementation. [Anthropic engineering article](https://claude.com/blog/seeing-like-an-agent)

The documented `AskUserQuestion` contract includes short headers, a full question,
two to four choices with descriptions, optional multi-select and user-authored
answers. The caller must preserve the original questions when returning answers;
custom text is the answer, not the word “Other”. These are useful interaction
requirements, not a requirement to adopt the Claude SDK. [Official SDK user-input documentation](https://code.claude.com/docs/en/agent-sdk/user-input)

Claude's guidance separates exploration, planning and implementation, allows plan
editing, and says small clear changes do not need the overhead of planning. It
also emphasises observable checks. For Jev, the transferable principle is an
adaptive interview: clarify meaningful uncertainty, then establish what will be
produced and how it will be checked. [Official best practices](https://code.claude.com/docs/en/best-practices)

## OpenCode: reusable source, not only visual inspiration

Inspected local checkout: `anomalyco/opencode`, commit
`d870e22c70f27103016dcd479edcfebf86136d93`. The root MIT notice is retained at
`research/licenses/opencode-LICENSE.txt`.

- [`question.shared.ts`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/cli/cmd/run/question.shared.ts)
  is a 340-line pure state machine. It separates request identity, question index,
  chosen labels, custom text, selected option, editing and submitting. A single
  single-select question can submit immediately; a sequence advances through
  questions and a review tab. A changed request ID resets the selection state.
  This is the strongest candidate for a small attributed Python port.
- [`question.shared.test.ts`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/test/cli/run/question.shared.test.ts)
  exercises immediate reply, multi-question review, toggling, custom text and
  request reset. Equivalent input/output fixtures can verify a port independently
  of Textual rendering. Add tests for unanswered questions, backwards edits and
  replacement of an already committed custom answer.
- [`QuestionPrompt`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/routes/session/question.tsx)
  maps that interaction into a question area: short tabs, full question, option
  descriptions, an additional custom editor, selection feedback and contextual
  key hints. Navigation and editing are different key modes. It avoids selecting
  a choice when a mouse drag was selecting text. Its OpenTUI/Solid runtime is not
  a drop-in component for Python/Textual.
- [`question/index.ts`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/question/index.ts)
  implements a pending request map. `ask` publishes an event and waits; `reply`
  resolves the matching request; `reject` fails it; disposal clears pending
  requests. Unknown or already answered IDs fail instead of answering the wrong
  question. Our persistence and cancellation need equivalent invariants even if
  the implementation uses a saved intake object rather than Effect `Deferred`.
- [`question` schema](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/schema/src/v1/question.ts)
  distinguishes generated prompt fields, runtime request identity and reply
  payload. Questions contain label/description options and optional multi-select;
  answers are arrays of labels in question order. The generated prompt does not
  need to produce the custom-entry option; the UI adds it.
- [`plan.ts`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/tool/plan.ts)
  makes the switch from plan to build explicit and injects the approved plan
  reference into the build conversation. Our equivalent should execute the
  exact reviewed revision, including user edits, rather than the initial vague
  sentence or a newly generated unseen plan.

Keep the copyright and MIT notice when copying or translating substantial code.
Record the exact source functions and local modifications. Do not describe a
Python reimplementation as a complete transplant of OpenCode. Do not transplant
Crush source under an unconditional MIT claim: the audited revision has an FSL
grant, documented in the earlier research.

One porting detail deserves care: the upstream custom-answer save path derives a
previous value from the editable custom slot. If edited draft text and committed
custom text are the same slot, replacing a multi-select custom answer can retain
the old chosen text. Our design should keep draft and committed values distinct
and test replacement; direct reuse should not mean copying defects.

## Proposed product flow

`Request → clarify when needed → editable brief and plan → start → work → evidence`

The planner should first inspect bounded existing context in a read-only process.
The conversational worker can generate task-specific questions and prose. Jev
returns typed decisions; it should route or evaluate readiness, not be presented
as a prose-generating model. The harness validates the structured payload and
owns the transition that permits execution.

An interview is one to three important questions per round. Ask about decisions
the user owns: desired output, available inputs and meaningful constraints. Do
not require a nontechnical user to choose a framework when the repository already
answers that question. Give a recommended option with a concrete consequence,
plus custom text and a “choose a sensible default” answer where appropriate. If
the user supplied the information already, do not ask it again. A clear request
can go directly to the plan, and an explicit direct mode can bypass the interview.

The question area shows one full question, a counter built as
`Question %d of %d · %s` from the index, the total and the question header
(`_render_question` in `jev_agent/intake_widgets.py`), two or three options with
short explanations, a multiline custom answer, and `← Back` / `Next →` /
`Later`. Choice and free-text editing have separate focus rules. Going back retains answers. Escape
leaves the question intact for later; it does not approve a default or run the
worker. A final review summarises the actual answers before plan generation.

The plan is a concrete brief, not a long transcript:

- **Result:** what the person can use afterward.
- **Inputs:** files or data already found, plus missing prerequisites.
- **Scope:** included behaviour and material assumptions.
- **Steps:** three to five outcome-oriented steps.
- **Verification:** commands or observable examples that will establish success.

The main action is **Start work**. The second is **Refine**; a correction can
return to clarification. A third, **Later**, dismisses the plan without
approving it. Retain the original sentence, each answer, the reviewed plan
revision and the eventual execution prompt in session artifacts. Resuming a
session restores the pending question or plan without starting work. Approval of
revision 2 cannot accidentally execute revision 1.

Example: “Хочу что-то полезное про крипту” (“I want something useful about
crypto”) should first establish whether the user wants a local portfolio tool,
data report or explanation. That phrasing is the `ROUGH_REQUEST` fixture in
`tests/test_guided_tui.py`. For a portfolio tool, clarify where transactions come
from and what report is useful. The resulting brief could specify a CSV reader,
holdings and fees, a Markdown report, malformed-row behaviour, sample data and a
repeatable test command. The recommendation is not a claim to have current market
data or permission to place trades.

## Visual hierarchy for the pink terminal

Use a slim header with session/project and one current state. Keep a compact
navigation affordance for sessions, files and Jev; avoid six large permanent
buttons above the transcript. The primary area changes with the task: question,
plan, active action, then answer. Keep a single composer with a clear contextual
action. Show line counts on expanded input or large pastes rather than taking two
permanent footer lines for an empty draft.

During execution, show the current user-oriented step and a compact event stream.
The existing expandable activity group remains useful. Exact commands, tool
output, Jev probabilities and graph remain available in details. Event counts and
internal phase names should not compete with the current task. After completion,
show the result, changed artifacts and the checks that actually ran. Put copy,
files and export beside that result or in its compact action row.

Pink is the accent for focus, selected options, the current step and the main
action. Use quiet charcoal backgrounds, readable foreground text and green/red
only for observed success/failure. No fabricated progress percentage or decision
trace. At 80×24, the question/plan body scrolls while the current action remains
reachable; the conversation should receive materially more height than before.

## Behavioural acceptance criteria

The critical behaviour is absence of a premature write: a vague request must not
start an implementing worker before the user reaches execution. Test the whole
boundary, not only rendering. Also verify custom multiline answers, back/edit,
request replacement, cancellation during generation, invalid structured output,
duplicate submission, pending-state restoration and plan revision fidelity.

For screen checks, use both 80×24 and a wider terminal. Verify the question,
focused choice and primary action are visible; no toolbar clips beyond the
viewport; multiline paste remains intact; resize and escape preserve draft text.
Record actual terminal state. Label a replay or mocked questionnaire accurately;
only a real planner response and real subsequent run establish the end-to-end
model path.
