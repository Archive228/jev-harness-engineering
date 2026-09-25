# Saved live experiments · 20 September 2026

- `inspect/`: Russian text, English questions from judge.py; one Jev request.
- `first-call-ru/`: Russian text and Russian questions from first_call.py; one Jev request.
- `primary-eval/`: the first frozen set, 18 requests / 28 decisions.
- `challenge-eval/`: a separately prepared, harder set, 18 requests / 28 decisions.
- `codex-matrix/`: real Jev and Codex, three defects, 8 Jev requests; two completions and one stop.
- `backend-recovery/`: a separate copy of the stopped state; both diagnostics and real Codex, with no new Jev request.

The set contains 46 Jev requests from these runs. The results are not combined into a general accuracy score: the first two requests demonstrate the primitives, the labelled sets check individual decisions, and the matrix checks the behaviour of the whole program. The method and the limits of the conclusions are in [VALIDATION.md](../../VALIDATION.md).

The requests, answers and logs were saved after the runs actually happened. Before distribution the absolute path of the author's directory was replaced with `<workspace>`, and the state references to projects were made relative to the packaged structure. Answer values, measurements, outcomes and hashes of the code that ran were not substituted. Keys and authorization headers are not part of these files.

The client was being refined between experiments. Early results may therefore lack the `usage_complete` and `usage_reported_requests` fields, which were added later. Their original format has been kept. The hashes in manifest/protocol refer to the code of a specific run; they need not match the latest state of the repository.

The recovery does not overwrite the original stop: see `backend-recovery/protocol.json` and `recovery.json`. The gallery and the article show both stages separately.
