# Jev Terminal v2 checks · 21 September 2026

What was checked is our own Python/Textual implementation. The sources of the four
upstream projects were studied separately; this protocol is not a claim that their test
suites were run.

## The agent's automated checks

**108 tests pass locally on Python 3.9.6.**
[Full output](./unit-tests.txt), [machine-readable result](./unit-tests.json).

Covered: real child processes and their cancellation, rerunning checks, contract
protection, corrupted logs and unfinished sessions, context selection, symlinks and
reading bounds, Noul ranking, assist/observe/off, plan, a retry with a new context,
saving the diff, export and drafts. The UI tests cover multi-line paste, sending, 80×24,
tool cards, search, session restore, file viewing and the display of completion and
errors.

The model answers in these tests are deliberately stubbed. Subprocess execution and
terminal events are checked for real. API calls are moved out into the live runs below,
so that a reader's tests need no key and burn no API quota.

## Live Crypto Ledger

Session **20260921-003736-ab8721** was run through the real TUI in a PTY. The request was
visible in the editor before sending; the calls began only after Ctrl+D. The session was
driven in Russian, so the saved session artefacts, the strings quoted from them below, the
screenshots and the finished tool's own CLI messages are in Russian; the Python test
outputs linked here are in English.

In the original teaching project **1 of 7** tests passed: [baseline](./crypto-baseline-tests.txt).
The contract and its tests were written before the agent was called. The first turn fixed
Decimal, fees, duplicates, timezones and the handling of invalid rows, produced the report
and 12 separate regression tests. The harness reran the saved contract and got 7 PASS on
an unchanged snapshot. Jev review proposed completion, and Python returned `accepted` with
a scope of «Только сохранённый контракт. Новое требование может выходить за его пределы.»
("The saved contract only. A new requirement may fall outside it.").

The first turn took **227.82 s**: 2 Jev calls, 1 worker, 2 runs of the contract command
(before and after the work). During that run we found that the outer `.gitignore` for
`.sessions/` excluded every file from the new retrieval. Codex carried on reading the
project with its own tools, but the source-Noul was not called in the first turn. This is
kept in the original `context.json`; the data was not replaced with a "successful" repeat.

The Git search boundary was fixed and covered by a regression test. The second turn of the
same session, through a new process, added to the README only. Jev received **5 real
candidates** and picked `README.md`, `report.json`, `ledger.py`. The real scores, paths,
line numbers and SHA-256 are saved. For example, the README got Noul **0.86**, the report
**0.73**, and ledger **0.46**. These are relevance scores for this request, not a
measurement of the program's correctness.

The second turn took **89.41 s**: 3 Jev calls, 1 worker, 2 contract runs. A real README
diff was produced, and the repeated acceptance passed. The new documentation section is
not covered by the original seven calculation tests: its content was additionally reviewed
and checked against the report's data.

## Independent reproduction of the result

After the model finished, the following were run again:

- [The 7 original contract tests](./crypto-contract-tests.txt): PASS.
- [The 12 tests added by the worker](./crypto-generated-tests.txt): PASS.
- [A real run of the CSV CLI](./crypto-cli.txt): exit 0;
  [the regenerated JSON](./reproduced-report.json).

The SHA-256 of the original `tests/test_contract.py` and `jev-checks.json` matched the
seed: [reproduction protocol](./crypto-independent-reproduction.json).
For BTC: balance `0.06`, cash flow `−3524.24 USDT`, fees `4.24 USDT`.
3 accepted rows in total, 1 duplicate and 1 rejected row. This is a synthetic accounting
example, not exchange data and not PnL.

## Saved evidence

[The portable session](./crypto-live-session/) holds the history, the JSONL, the real Jev
request/response pairs, the worker stream, the check results, the snapshots and the
finished workspace.
[The summary of the two turns](./live-summary.json) keeps the statuses, the timings and the
provider usage. The token counters are provider data, and no price was computed from them.
In the published text logs the root of the author's checkout is replaced with
`<checkout>`; the finished tool's code is kept without rewriting.

To reproduce the finished tool without models:

```bash
cd terminal-agent/verification/v2/crypto-live-session/workspace
python3 -B -m unittest discover -s tests -v
python3 -B -m unittest discover -s regression_tests -v
python3 -B cryptoledger.py examples/trades.csv --json report.json
```

A fresh independent run of the agent: `./jev --mission cryptolab`, then F2 and Ctrl+D.
You can carry on with the archived workspace through `--resume` with its absolute path;
for your own experience a new copy of the mission is preferable.

## Screenshots

`../screenshots/terminal-v2-*.svg` holds the real Ctrl+S screens: the full draft with zero
calls, the commands during the work, the Jev panel, the accepted result, the context, the
file selection, the original text and the diff. The PNGs with the `browser` suffix are
captures of these SVGs rendered in a browser. These are not hand-drawn mockups.
Three local `*-preview.svg` files were intermediate headless previews and are not part of
the published set. They cannot be used as proof of a live call.

The observe/off/plan scenarios, cancellation and a retry after a diagnostic triage are
covered by automated tests. The two live turns above used assist/auto and each passed on
the first worker attempt. No live A/B benchmark of a Jev speed-up is claimed here, nor
exhaustive correctness on arbitrary projects.
