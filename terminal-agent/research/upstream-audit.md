# Jev Terminal: a study of the Pi, PiJev, OpenCode and Crush sources

Date of the study: 21 September 2026. This is a study of specific checkouts, not a promise of features taken from a changing README. The sources were read locally, the upstream programs were not run, and their tests were not executed as part of this audit. The checks on our own agent are described separately in `verification/`.

## The conclusion for our product

The most useful thing to borrow is how the work is organised, not just a colour theme: one conversation feed, one updatable card per tool call, expandable output, separate saved events, a workable editor and access to previous sessions. The user has to see what the agent actually did, how a command ended and where the result sits. The graph and Jev's probabilities help explain the process, but they must not permanently take half the screen away from the conversation.

For this version it makes sense to keep our Python/Textual + Codex runtime and carry over the mechanisms that fit. A full move to Pi/PiJev would give more ready-made capability, but it would at the same time replace model invocation, authorisation, session storage, tools and the UI. That is a separate migration, not installing a theme. OpenCode is considerably wider still: the TUI, the server, the SDK, SQLite, plugins, providers, permission control and workspaces form one system.

Jev stays an explicitly visible decision layer. The user has to be able to tell apart "Jev picked the sources", "Codex ran the command", "the harness ran a test" and "Jev proposed completion". One green tick must not merge those different facts.

## What was actually studied

The pinned versions:

- **Pi**: `f5c946480c575604c50d810adc88b11679d6aecb`, [the repository at this commit](https://github.com/earendil-works/pi/tree/f5c946480c575604c50d810adc88b11679d6aecb).
- **PiJev**: `0b67ff916fb9c6cadd4d939b8a7a14976252efef`, [the repository at this commit](https://github.com/tonyzdev/pijev/tree/0b67ff916fb9c6cadd4d939b8a7a14976252efef).
- **OpenCode**: `d870e22c70f27103016dcd479edcfebf86136d93`, [the repository at this commit](https://github.com/anomalyco/opencode/tree/d870e22c70f27103016dcd479edcfebf86136d93).
- **Crush**: `afb55f03c5f510bebeb04197ee05fbe540384db8`, [the repository at this commit](https://github.com/charmbracelet/crush/tree/afb55f03c5f510bebeb04197ee05fbe540384db8).

An inventory through `git ls-files`, counting lines in tracked `.ts/.tsx/.js/.mjs/.go/.py/.zig`, gave: Pi, 1,537 files / 362,720 lines; PiJev, 115 / 8,740; OpenCode, 3,344 / 683,680; Crush, 670 / 157,185. That is source together with tests and fixtures, and the number is not an estimate of production-code complexity. The total is 1,212,325 lines. They were not all read. The relevant end-to-end paths were examined: startup, the agent loop, tool events, history storage, the terminal editor, tool rendering, error handling and extension points. In the remaining files we used symbol search and dependency navigation.

PiJev is especially convenient to study in detail: the whole of its `src/` is 1,239 lines across ten files. It inherits most of the agent itself from Pi. Its `package.json` pins **Pi 0.85.1**, while the Pi checkout we studied also contains a new harness with lanes and JSONL v4. You cannot automatically assume that every new Pi API in that checkout is available to PiJev 0.1.0. [PiJev dependencies](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/package.json).

## Pi: the event model and a good terminal layer

### How a request gets through

`packages/coding-agent/src/main.ts` parses the arguments, picks a session manager, creates services/runtime and passes the runtime to `InteractiveMode`. That is an important boundary: the terminal must not own model calls itself. Our `JevApp` → `Session` split already follows the principle. [Entry point](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/main.ts#L566).

On the classic path `AgentSession` subscribes to agent-core events, stores messages and exposes a subscription to the UI. In `agent-loop.ts` the inner loop executes tool calls, returns tool results into the context and calls the model again. The outer loop picks up a follow-up after a natural end. Steering and follow-up are delivered at different moments. Tool arguments truncated by the token limit are not executed as full calls: the loop produces errors for those tools. [The agent loop](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/agent/src/agent-loop.ts#L161).

### Why the logs are readable

`AgentEvent` has separate `tool_execution_start`, `tool_execution_update` and `tool_execution_end`, and all of them carry **toolCallId**. `InteractiveMode.pendingTools` is a map keyed by that ID. Start creates a card, update changes its contents, end sets the result and removes the call from the unfinished list. Several updates from one process do not turn into several independent commands. [Event types](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/agent/src/types.ts#L458), [handling in the terminal](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/interactive-mode.ts#L3412).

`ToolExecutionComponent` keeps the arguments separate from the result, can accept a partial result, can render an error, can show a compact preview and can expand the rest. The user sees what is hidden and how to expand the output. A registered tool can define its own `renderCall` and `renderResult`, and there is a shared fallback. [The tool card](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/components/tool-execution.ts#L156).

In our original `runtime.py` the `item.id` from the Codex JSONL was being lost. That is the main structural obstacle to a good UI. We need an ID that is unique within a turn and a worker attempt, and for checks the harness needs an ID of its own. Cards must not be linked by the text of the shell command: the same command is legitimately run more than once.

### The editor and history

Pi has a separate Editor with Unicode/grapheme-aware navigation, soft wrap, undo, history, autocomplete and bracketed-paste handling. `CustomEditor` adds the application's own keys, and Escape first closes autocomplete and only after that can interrupt the agent. The working status can live in the editor's top border instead of a separate large panel. [Editor](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/tui/src/components/editor.ts), [CustomEditor](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/components/custom-editor.ts).

Pi can collapse large pastes into markers. **For us that must not become the default behaviour:** the user has already asked to see the whole message. What is useful is keeping the original, inserting line breaks correctly, scrolling, expanding the editor and history. Hiding a long request behind `[paste #...]` contradicts the current request.

The session manager stores append-only entries with `id`/`parentId`, model changes, compaction and branch summaries. A CustomEntry can be stored without entering the LLM context, and CustomMessageEntry controls the model context and the display separately. Those are three different layers: durable history, context, presentation. [The session format](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/core/session-manager.ts#L40).

For now our agent is well served by linear JSONL and resume. Branching, compaction and a full continuation of a native model session cannot be promised merely because we save events. Our Codex starts with `--ephemeral`, and the next turn receives text context from the saved history plus the workspace files. That is a limited continuation, not a restoration of every internal Codex message.

### Extension

Pi provides event hooks, custom tools, slash commands and UI renderers. PiJev uses exactly those boundaries. Carrying the whole dynamic plugin system into our teaching agent is not necessary: explicit Python boundaries are enough for preparing context, the Jev decision, running the worker, the check and the projection of events. If the runtime changes later, that lets you replace the adapter without rewriting the terminal.

## PiJev: the most useful source of Jev features

### The actual architecture

`cli.ts` loads the configuration and calls Pi's `main` with `extensionFactories: [{name: "pijev", factory: ...}]`. The `createPijevExtension` function hooks into session start/shutdown, before_agent_start, context and tool_result, and registers `/pijev` and `pijev_search`. Pi's generative model stays the executor. [CLI](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/cli.ts#L94), [extension](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/extension.ts#L14).

### Source search

The search first builds real candidates and only then hands them to Jev. Literal search calls `rg --fixed-strings --json` and returns the path, the line numbers and an excerpt. Discovery enumerates the available files, performs a bounded read, ranks the files lexically through BM25 and builds a shortlist. Jev does not invent paths or code. A Noul question is asked about the relevance of every candidate that exists. The result is sorted by the value returned. [Literal search](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/search.ts#L25), [discovery](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/discovery.ts#L240), [rankCode](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/decisions.ts#L71).

There are exact limits: discovery enumerates up to 20,000 files, reads up to 48 MiB in total and up to 256 KiB per file, and spends no more than 8 seconds on the reading stage; the shortlist is 100 files by default. An excerpt is capped at 1,800 bytes and an outline at 1,200. This is not a full survey of the repository, and upstream marks the incomplete coverage explicitly.

Ranking is split into requests up to an internal payload limit. If one batch fails, the partial "smart ordering" is discarded whole and the original list is returned. That approach prevents the situation where the half of the candidates that got scored gains an unfair advantage over the half that did not.

The automatic source briefing shows at most three different files. For a confident top candidate the full file is allowed within 50 KiB. The hint is tied to a specific user-message ID and is inserted next to that request rather than repeated after every tool. Comments and source are marked explicitly as data, not as instructions.

**Adapting for Russian is mandatory.** In the `discovery.ts` we studied the tokenizer understands Latin and Han but not Cyrillic. A Russian query with no English identifiers yields a poor or empty set of lexical terms, and Jev cannot rescue a file that never reached the shortlist. Our variant needs Unicode tokens and a check on a Russian query. A plain word match, even with a good Jev score, does not prove that the one correct file was picked.

### Skills and error diagnostics

Skill selection has two stages: the short descriptions give a shortlist, then the bounded instructions of the top candidates are read and their actual usefulness is checked. A skill the user picked explicitly takes priority, and the whole roster stays available. That is a good general principle, but we do not need a fake `/skills` until the executor really can receive and apply the selected instructions.

Failure triage runs only after an error tool result, at most twice per turn, and does not analyse its own `pijev_search`. Jev picks one of the categories code/environment/dependency/network/permission/unknown. A cautious, pre-written hint is returned only if confidence and probability clear the thresholds. The diagnosis is marked as a guess, not a confirmed root cause. [DecisionEngine](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/decisions.ts#L105), [tool_result hook](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/extension.ts#L167).

In our Codex subprocess you cannot simply insert a Pi extension hook and step in between any two internal tool calls. For now the sensible integration point is after a worker attempt or a harness check finishes, before the next attempt. Visually, such a diagnostic must not be presented as real-time control over every shell command.

### Modes, cancellation and transport

PiJev supports `assist`, `observe` and `off`. Observe makes the requests and records metadata but does not apply the recommendations, and off does not call Jev at all. That gives a useful comparison baseline, but observation in observe alone is not enough to prove a gain in quality or cost. You need identical tasks and measurable outcomes.

JevClient has a bounded request/response, a timeout, a shared AbortSignal, validation of types and probabilities, a cache keyed by the SHA-256 of the full body for five minutes, at most 128 entries, and a cooldown after a run of failures. By default a request is capped at 1,800 ms, the payload at 90 KB and the response at 1 MB. A failure of an optional advisory returns an explicit fallback. [JevClient](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/jev.ts#L67).

That is not an argument for weakening our mandatory Jev route/review: the failure boundaries are different. If the optional source ranking is unavailable, you can carry on with the lexical shortlist and show the fallback. If the mandatory decision gate did not return a valid result, you must not draw a successful Jev answer.

DecisionJournal writes a separate allowlist of metadata: mode, kind, status, latency, token usage, sessionId and userMessageId. It does not write source, prompts or answers. Our article's task requires detailed evidence, so raw local evidence is saved separately, while the compact UI and the export have to pick the minimum needed. Upstream does not count cache-hit tokens as spent a second time. [The decision journal](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/telemetry.ts#L20).

## OpenCode: separating the conversation from the detail

In the version we studied the terminal frontend lives in `packages/tui` and the main session in `packages/opencode/src/session`. The old path `packages/opencode/src/cli/cmd/tui`, which is still widely cited, is wrong here.

`prompt.ts` assembles the user message and starts the session loop, and `processor.ts` converts stream events into stored message parts. A tool part has a `callID` and the states pending → running → completed/error. Start records the time, result writes the output, title, metadata and attachments, and abort closes unfinished calls. The UI receives data through the SDK/sync. A screen redraw is therefore not the same thing as running a command. [Session loop](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/session/prompt.ts#L1081), [processor](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/session/processor.ts#L236).

Repeated identical tool calls are detected separately from the model. There is compaction, recovery of interrupted tools, a retry status and storage of the session structure in SQLite. None of that can be replaced by a label reading "smart memory". What suits our agent now is explicit attempt limits, no-progress detection and linear storage of the result.

The terminal session view manages the sidebar, timestamps, tool details, generic output and per-message scrolling separately. Generic tool output is hidden by default and the user can expand it. The preview limit counts lines and characters at the same time. The principle suits us, but an important error and the exit code have to stay visible without expanding anything. [Session UI](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/routes/session/index.tsx#L256), [output limiting](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/util/collapse-tool-output.ts).

Prompt history and stash are separate JSONL files holding the last 50 records each. The parser skips corrupted lines, a repeat of the previous prompt is not duplicated, and history navigation must not overwrite a current draft that differs. The stash also keeps the parts and the timestamp. Submit has a double-send guard: otherwise two concurrent sends before the editor is cleared can create a spare empty session. [History](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/prompt/history.tsx), [stash](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/prompt/stash.tsx), [submit guard](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/component/prompt/index.tsx#L930).

OpenCode represents files, pastes and images as prompt parts bound to editor ranges. A large paste can be collapsed into `[Pasted ~N lines]`. As with Pi, for us that is a useful mechanism for keeping the data but a poor display default. Reading a path out of the clipboard automatically is not needed either: an explicit command for adding a file is clearer for our reader.

The session picker has search, shows the selected session and works from metadata rather than reading all the large raw logs to draw the first screen. What is useful for us is `/sessions`, selection by title or date, and a local export of the report. Resume has to load the selected workspace and history, not quietly create a new task.

OpenCode's plugin API contains server hooks, custom tools and workspace adapters. Copying it apart from the server and SDK will not give working extensibility. In this version it is a reference for the interfaces, not a module you can plug into our Python runtime. [Plugin types](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/plugin/src/index.ts).

## Crush: behaviour details that matter

Crush uses Go, Bubble Tea, Lip Gloss, Fantasy and SQLite. `internal/agent/agent.go` ties generation events to the message service: tool-input creates a ToolCall, a finished call updates the input, and ToolResult is stored separately and linked by ToolCallID. On cancellation the tool results are saved through the live parent context, so that the cancelled generation context does not destroy the evidence of actions already performed. [Runtime handlers](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/internal/agent/agent.go#L920).

Details worth reproducing in an implementation of our own:

- A command and its stdout are different visual elements. In `bash.go` the text of the shell command itself stays visible while the output can be collapsed. The checks on that behaviour sit next to it in `bash_test.go`.
- FinishReason distinguishes normal end, token limit, cancellation, error and provider refusal. An empty answer after a refusal does not look like successful silence. [Message types](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/internal/message/content.go#L31).
- Retry clears the partial streamed content before retrying, so that two attempts do not glue together into one apparently coherent answer.
- A session stores `EstimatedUsage`, and the interface can show that the spend is approximate. Our `usage_complete=false` has to be visible too.
- The session picker has a proper list, search and filtering, renaming, and separate action modes. [Session dialog](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/internal/ui/dialog/sessions.go).
- Loop detection looks at repeating tool input/result pairs, not just the command name. Running `pytest` again after a real repair is not the same as looping. [Loop detection](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/internal/agent/loop_detection.go).

Crush sources are not copied into the product, for the reasons set out below. The existence of a separate open component of the Charm ecosystem does not mean the whole of Crush carries the same licence.

## What to carry into our agent first

**The base for usability and verifiability.** The conversation feed; compact tool rows with identity and lifecycle; expanding the detail; visible errors; a multi-line editor; the raw JSONL kept separately; a compact status; a graph built only from events that actually arrived. The UI has to project live events and saved history the same way, without calling models on load.

**Features for daily work.** Session picker and resume, a history of sent requests that preserves the current draft, a command palette, file context added explicitly, a list of changed files, a Markdown export with paths to the evidence. These features help the user finish a piece of work and come back to it, rather than just watch a good-looking run.

**A more substantial role for Jev.** A bounded source shortlist of real files plus Noul ranking; a bounded diagnostic aimed at the checks that actually failed; a transparent purpose, model, duration and fallback. These stages have to pass useful data to the next worker attempt, otherwise all we get is decorative model calls.

**Separate architectural work.** Switching provider directly, native model-session resume, compaction, branching, undo of working files, MCP, parallel subagents, background jobs and dynamic plugins all require new contracts. A button with no working implementation behind it does more harm here than no button. A SHA-256 snapshot proves that something changed, but it does not restore the original contents, so it cannot be called undo.

## The limits of a correct transfer

The licences were checked in the local checkouts. Pi is MIT, copyright Mario Zechner; PiJev is MIT, copyright PiJev contributors; OpenCode is MIT, copyright opencode. Carrying over substantial source code requires keeping the corresponding copyright and licence notice. This research note describes mechanisms, and no upstream production source is copied into it. [Pi LICENSE](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/LICENSE), [PiJev LICENSE](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/LICENSE), [OpenCode LICENSE](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/LICENSE).

Current Crush carries **FSL-1.1-MIT**, with a Competing Use restriction and a transition of each specific version to MIT after two years. A separate historical MIT notice in the same file does not make the whole current checkout MIT. For this work we chose one concrete practical approach: no Crush source code is carried over, and only observations about interface behaviour are used. [Crush LICENSE](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/LICENSE.md).

Apart from licences, the behaviour has to be honest. Jev's confidence is not the probability that the whole application is free of errors. Model-generated tests do not turn into independent acceptance. Hiding the reasoning in our runtime stays: the screen shows tools, the actual checks and explanations of the result that were composed explicitly, and it does not claim access to the model's hidden thinking.

## What checks the carried-over mechanisms need

These are criteria for the quality of the implementation, not a report of tests already passed:

1. Start, update and end for one tool ID produce one card; the same command repeated under a different ID stays a separate call; identical raw IDs in different attempts do not merge.
2. A cancellation or an error closes the running state, keeps the output already received and does not mark the tool as successfully completed.
3. A saved session opens with no API calls; old-format events without an ID are still readable.
4. Pasting a multi-line Russian request does not send it automatically, does not change its line breaks and does not hide the text behind a single placeholder.
5. History and session selection do not destroy a non-empty draft; pressing send twice does not start two workers.
6. Source context is bounded by files and bytes, does not follow a symlink outside the workspace, excludes credentials and accepts Cyrillic in the query; an old excerpt is not presented as current after the file has changed.
7. A failure of the optional Jev ranking leaves a marked lexical fallback; a failure of the mandatory decision gate does not become a fake Jev result.
8. The export contains real statuses and paths to the evidence; the arguments and output on display are stripped of terminal control sequences and of obvious secrets.
9. A narrow 80×24 screen keeps access to the conversation, to sending and to errors. The full screen does not depend on a debug panel being open.

The study shows which parts can genuinely be carried over to useful effect. Which of them are already implemented in our checkout is settled by the current code, the README and the test results. Mentioning an upstream feature is not by itself a claim that we have it.
