# Terminal interaction research, 21 September 2026

This is an audit of specific execution-to-interface paths, not a claim that every
line in three large repositories was understood or exercised. The repositories
were cloned locally and inspected at the commits below. The findings informed an
independent implementation in Python/Textual; no upstream source was copied into
`jev_agent/tui.py` or `jev_agent/ui_widgets.py`.

## Pi: conversation and tool lifecycle

Commit: `f5c946480c575604c50d810adc88b11679d6aecb`; root license: MIT, Mario Zechner.

Inspected:

- [`interactive-mode.ts`](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/interactive-mode.ts), especially the `message_start`, `message_update`, `message_end`, and tool start/update/end handlers.
- [`tool-execution.ts`](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/components/tool-execution.ts): stable tool-call identity, separate argument/result state, pending/error presentation, collapsed result preview, and expansion.
- [`assistant-message.ts`](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/components/assistant-message.ts): Markdown prose separated from tool execution presentation.
- [`custom-editor.ts`](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/components/custom-editor.ts), plus the paste/history/undo paths in `packages/tui/src/components/editor.ts`.
- [`session-selector-search.ts`](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/components/session-selector-search.ts): search matching and the distinction between recency and relevance.

The strongest transferable mechanism is the pending-tools map. One actual call
owns one visual component; subsequent updates modify it rather than append
duplicate transcript entries. Error/abort completion also resolves pending tool
components. In our adapter, provider item IDs can repeat across attempts, so the
map is keyed by `call_id` plus `item_id`. Legacy events with no identity remain
separate because merging by command text would invent a relationship.

The prose/tool split is also useful: an answer benefits from headings, paragraphs,
lists and fenced code; a shell result must remain literal. Our `ConversationCard`
uses Markdown only for worker/assistant messages, while user input, errors, event
JSON and tool output use sanitized literal `Text`.

Pi's editor is a different terminal engine and is not transplanted. In particular,
large pasted text can become paste markers in Pi. This project deliberately keeps
all pasted lines visible, retains Enter as newline, and uses Ctrl+D or a button to
submit, because that is an explicit requirement from our user.

## OpenCode: discoverability, context and history

Commit: `d870e22c70f27103016dcd479edcfebf86136d93`; root license: MIT, opencode.

Inspected:

- [`command-palette.tsx`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/component/command-palette.tsx): reachable commands, descriptions, keybindings, suggestions, and filtered selection.
- [`dialog-session-list.tsx`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/component/dialog-session-list.tsx): recent sessions, search queries, current session inclusion and session navigation.
- [`prompt/index.tsx`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/component/prompt/index.tsx): prompt state, submit serialization, draft retention, paste handling, and editor-to-command boundaries.
- [`prompt/stash.tsx`](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/prompt/stash.tsx): persistent bounded drafts, parser recovery and explicit restoration.
- `packages/tui/src/routes/session/index.tsx`: inline tool state, actual execution metadata and subagent status presentation.

Our command picker has one searchable list that exposes real commands and their
descriptions. Selecting a mode calls `Session.configure`; it does not insert a
pretend command into a chat transcript. Session selection saves the current draft,
loads the target session, clears display state and event identities, restores that
session's draft, and never starts work automatically. Busy sessions cannot switch.

We added one persistent draft per session, rather than copying OpenCode's full
stash history and attachments architecture. Draft storage uses the catalog's
bounded atomic local write. Restoring a draft is not permission to run it. File
inspection similarly opens literal bounded source and saved diffs; it does not
execute file contents or manufacture diffs for older sessions.

## Crush: readable hierarchy, not transplanted source

Commit: `afb55f03c5f510bebeb04197ee05fbe540384db8`.
Read `LICENSE.md` before source inspection: current source is FSL-1.1-MIT with a
future MIT grant, including a competing-use restriction. It is not treated as
unconditionally MIT today. No Crush code, styling definitions or assets were
copied or translated into this product.

Inspected UX-related definitions in `internal/ui/chat/tools.go`, `bash.go`, and
the rendering/caching structure in `assistant.go`. The useful high-level ideas
are that tool work has a distinct compact visual identity, pending and error
states differ, long output can expand, and a conversation should remain readable
without a wall of diagnostics. Our independent Textual design applies those
general interaction ideas with its own components, layout, palette and behavior.

## What the implementation actually adds

The primary view is a full-width conversation, a short rail of observed phases,
and a multiline editor. A hidden drawer exposes three views: Jev answers and
probabilities with the execution graph, checks/files, and exact stored events.
Jev decisions are also summarized inline so the reader can see their causal role
without opening the drawer. Observe mode is explicitly labelled as not applied.

Tool cards update by actual lifecycle, preserve exit codes, and expand to literal
output. `finished` and `lifecycle=completed` are terminal; a cancelled/error turn
marks unresolved calls as stopped rather than leaving fake running indicators.
The interface does not make up progress percentages, chain-of-thought, costs, or
confidence estimates. It renders the telemetry that the backend emits.

F1/Ctrl+P opens command search; F3 opens raw events; F6 opens details; `/sessions`
opens session search; `/files` opens a source/diff browser; `/export` saves the
conversation locally. Ctrl+S still exports the actual current terminal screen.
At 80×24, the drawer takes the conversation area while preserving the composer;
at wider sizes it sits beside the conversation. F4 gives the draft the main area.

Tests exercise real widget events, pasted multiline text, lifecycle coalescing,
interruption, drawer resizing, Markdown/literal boundaries, draft restoration,
command filtering, artifact browsing, busy-state restrictions and session changes.
Network/model calls are fakes in tests only. Saved-history screenshots use actual
previous session events and are labelled as restored or recorded views, not new
live model executions.
