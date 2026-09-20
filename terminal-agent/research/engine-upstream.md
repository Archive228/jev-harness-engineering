# Backend source study and adaptation

Read on 2026-09-21. This is a study of the relevant execution paths, not a claim to have read every file in either repository.

Pinned upstreams:

- PiJev: `0b67ff916fb9c6cadd4d939b8a7a14976252efef` (MIT), <https://github.com/tonyzdev/pijev/tree/0b67ff916fb9c6cadd4d939b8a7a14976252efef>.
- Pi: `f5c946480c575604c50d810adc88b11679d6aecb` (MIT), <https://github.com/earendil-works/pi/tree/f5c946480c575604c50d810adc88b11679d6aecb>.

## Paths traced

PiJev `src/extension.ts` registers the session command, resets cancellation and advice at `before_agent_start`, then performs optional initial evidence discovery in the `context` hook. It anchors that evidence beside the user message that caused it; it does not continuously append stale advice. The `pijev_search` tool combines actual retrieved excerpts with a separate judgment pass. `tool_result` performs at most two advisory failure classifications in one run. A captured mode and abort signal prevent asynchronous answers from affecting a later session or mode.

`src/search.ts` uses literal ripgrep matches with path/line attribution, generated-directory/credential exclusions, byte/time limits, and explicit partial-coverage reporting. `src/discovery.ts` broadens natural-language discovery through bounded file enumeration, identifier tokenization and lexical ranking. Its shortlist is a recall ceiling: Jev cannot recover a file that was never retrieved.

`src/decisions.ts::rankCode` asks one Noul relevance question per real candidate, validates complete batch results and only reorders supplied evidence. `triage` asks a typed category question; its hint is gated by confidence and selected-option probability and is explicitly not a verified cause. `recommendSkills` has a two-stage shortlist and instruction verification; this adaptation does not import skill execution.

`src/config.ts` and the extension's mode checks define `assist` (advice can affect context), `observe` (record but do not apply), and `off` (no model calls). An observation must not silently change ranking or execution.

Pi `packages/agent/src/agent-loop.ts::executePreparedToolCall` emits real start/update/end lifecycle events sharing `toolCallId`. `packages/coding-agent/src/core/agent-session.ts` forwards these events and applies extension tool-result hooks. `packages/coding-agent/src/core/extensions/runner.ts::emitToolResult` composes hook results. These are the references for stable tool-card identity, not a reason to invent token streaming or hidden reasoning.

## Adapted here

The Python implementation independently reproduces the bounded retrieval → typed relevance → real worker pattern, a diagnostic failure category carried into the next attempt, three Jev modes, and stable event IDs. It keeps the existing Codex subprocess and TypeSafe transport. Our `plan` mode is an explicit read-only execution policy; Jev cannot override it. Registered checks and file-mutation checks remain authoritative in every mode. Optional retrieval/triage failures fall back visibly; mandatory route/review failures in assist mode remain errors. Source context is refreshed before each retry, with separate `attempt-NN-context.json` evidence. Started API/worker attempts are counted immediately; failed calls remain counted and unknown token usage stays explicitly incomplete.

This is an intentionally smaller design: five candidates, three selected snippets, no BM25 index, no skill/plugin execution, no model-provider replacement, no new runtime dependencies. Russian and Latin query tokens are supported without inventing translations. Partial coverage and missing matches are reported. Diffs are local evidence captured with independent size/secret/path limits; unavailable old content is never reconstructed. The selected workspace is the ignore-rule boundary: native Git exclusion rules apply when it is the repository root; a nested or session workspace uses only its own local/nested conservative `.gitignore` rules. A containing repository's `.sessions/` exclusion must not erase that session's entire source shortlist.

No upstream implementation text was copied into the runtime. Behavioral inspiration and source attribution are recorded here; any future direct copying must retain the relevant MIT notice.

## Local verification

On 2026-09-21: 40 engine tests and 11 context tests passed on Python 3.9. These use real temporary files/subprocesses and explicit fixture model transports; they do not represent new live Jev/Codex calls. Coverage includes observe/off invariants, plan mutation prevention, diagnostic propagation and refreshed source context in a second attempt, low-confidence advice marked unapplied, ranking boundaries, Russian queries, symlinks/credentials/binary/ignore exclusions, ignored containing repositories, native root exclusions, capture limits and hashes, tool lifecycle identity, in-flight and failed call counts, corrupt-event recovery, orphan-turn recovery and last-session selection. Live validation is a separate integration step.
