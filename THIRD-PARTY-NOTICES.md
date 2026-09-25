# Third-party code and its licenses

Our own code in this repository is distributed under MIT (the `LICENSE` file). Below is
everything third-party that is present here, and on what terms. A machine-readable version
with exact commits is in `terminal-agent/research/upstreams.json`, and the breakdown of what
was borrowed is in `terminal-agent/research/ATTRIBUTION.md`.

## Code included in the tree

These files are physically present in the repository together with their licenses. The
`terminal-agent/vendor/` directory is the only place that holds third-party source code.

| Source | License | What is included | Where |
|---|---|---|---|
| OpenCode (c) 2025 opencode | MIT | `question.shared.ts`, the original single-choice state machine, ported to `jev_agent/question_state.py` | `terminal-agent/vendor/opencode/` |
| Hermes (c) 2025 Nous Research | MIT | `clarify_tool.py`, the original clarifying-question mechanics | `terminal-agent/vendor/hermes/` |
| OpenAI Codex (c) 2025 OpenAI | Apache-2.0 | the `request_user_input` specification and the schemas of its parameters | `terminal-agent/vendor/codex/` |

Apache-2.0 requires passing on a copy of the license and the contents of NOTICE to the
recipient, and marking the changes that were made. The copy of the license and NOTICE are in
`terminal-agent/vendor/codex/`, and the changes are described in
`terminal-agent/vendor/codex/ADAPTATIONS.md`. The Codex NOTICE in turn passes on attribution
to Ratatui (MIT, (c) 2016-2022 Florian Dehau, (c) 2023-2025 The Ratatui Developers).

## Projects studied as references

The source code of these projects is not included in the repository. We read their code and
implemented close ideas ourselves in Python. Copies of the licenses are kept in
`terminal-agent/research/licenses/` for traceability.

| Project | License | Role |
|---|---|---|
| PiJev (c) 2026 PiJev contributors | MIT | an agent with Jev in the loop: how retrieval and questions are arranged |
| Pi (c) 2025 Mario Zechner | MIT | agent loop, context management, input editor |
| OpenCode (c) 2025 opencode | MIT | how the interface and sessions are organised |
| Crush (c) Charmbracelet | FSL-1.1-MIT | styling of the terminal interface |

A note on Crush: the Functional Source License 1.1 permits use but forbids competing use, and
a given version passes to MIT two years after its publication. There is no Crush code in our
tree, which was verified by comparing n-grams across the whole of `jev_agent` against 706
upstream files: the maximum shared 5-gram count is 3, and it falls on generic API field names.

## Runtime dependencies

`terminal-agent/requirements.txt` pins Textual, Rich, Pygments, markdown-it-py and their
transitive dependencies, all under MIT or BSD. The `jev-harness-lab` library has no external
dependencies: the standard library only.

## External services

The agent calls Jev (TypeSafe, `api.typesafe.ai/v1/systemone`) and the Codex CLI. These are
third-party services with their own terms of use. Neither of them is part of this repository,
and neither is covered by its license.
