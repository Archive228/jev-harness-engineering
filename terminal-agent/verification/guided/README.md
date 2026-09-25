# Idea → questions → plan → work · 21 September 2026

A real Python/Textual terminal interface was verified with the Codex CLI and the
TypeSafe API, Jev model `jev-1.13.0`. The screens were captured during a live run
with Ctrl+S. The PNGs are browser screenshots of the resulting SVGs, not mockups.

## What was entered and what came back

The original request, typed in Russian: **«Хочу что-нибудь полезное про крипту,
чтобы запустить прямо в терминале.»** ("I want something useful about crypto, to
run right in the terminal.") This run was done in Russian: the interface, the
questions and the saved session artefacts are in Russian, and the English
wordings in this file are glosses. The method notes, the test output and
ATTRIBUTION.md are in English. The planner asked one question:
calculate profit or track a portfolio. After the explicit choice «Считать
прибыль» ("Calculate profit") and the answer review, it drafted a plan for a
terminal calculator of one purchase and one sale, with fees and checks.

The first preparation took **30.19 s**, the second **31.89 s**. Both used the real
Codex in read mode. Until the plan was accepted the workspace stayed empty: the
snapshots before and after both preparations match, and **0** files were written.
At this stage there were **0** Jev calls. The raw answers and requests are saved
in [live-session/intake](./live-session/intake/).

The process was closed on the finished plan and started again with `--resume`. The
plan was restored without starting work. Then the «Начать работу» ("Start work")
button was pressed explicitly. The exact [approved request](./approved-request.md)
matches `text` in the [execution request.json](./live-session/turn-003/request.json).

Execution took **140.20 s**: **2 Jev calls, 1 worker call**, then a check of the
tests it created. An empty project needed no ranking of source files. Jev route
chose the action, and Jev review proposed completion. The worker created
`crypto_profit.py`, `README.md` and `test_crypto_profit.py`.

The harness outcome: **`ready` / «Результат подготовлен»** ("Result prepared").
There was no pre-registered independent contract during the work, so the result
is not presented as `accepted`. The worker's own **9 tests** passed. The full log
also keeps a failed intermediate worker command; it is not removed from the
record.

## Independent verification of the result

After the work finished, a separate reviewer ran **47 cases through the CLI**,
with the expected numbers set independently of the implementation. **47/47
passed**:

- Without fees: buying 2 × 100 and selling 2 × 120 → profit **40.00**, **20.00%**.
- 1% on each side → costs **202.00**, proceeds **237.60**, fees **4.40**,
  profit **35.60**, return **17.62%**.
- Loss, zero profit, zero sale price, a fractional quantity, a decimal comma,
  unequal fees and a valid fee of 99.99%.
- 34 invalid-input cases where the value is asked again: strings, NaN,
  infinity, negative values, invalid zeros and fees.
- EOF at each of the five input steps: a clear cancellation with no traceback.

The **9/9 tests** created by the worker were rerun separately. The hashes of all
three source files were unchanged. [Method, harness and results](./independent/README.md).
This is an after-run check; it does not change the historical status of the live run.

To repeat this without keys or models, from `terminal-agent/`:

```bash
python3 verification/guided/live-session/workspace/crypto_profit.py
python3 -B verification/guided/independent/check_cli.py \
  verification/guided/live-session/workspace --output /tmp/jev-calculator-checks
```

## Checks of the agent itself

**191 automated tests passed on Python 3.9.6.**
[Output](./unit-tests.txt), [run metadata](./unit-tests.json).
They check real Session + IntakeController + Textual transitions; the model
answers in the tests are explicitly replaced with test fixtures. The service
calls are verified by the separate live run above.

Covered: the questions, a multi-line answer of your own, the answer review,
refining the plan, the exact task for the worker, running only the accepted
version, protection against a double start, a changed project, restoring a
draft, read mode, cancellation including before the first model call, task
overflow without losing answers, a plain answer with no execution, old sessions
and the 80×24 screen. The existing checks of the processes, the contracts and
the Jev modes also pass.

CI runs the main suite on Python 3.9 and 3.13, then repeats the independent CLI
checks of the saved calculator. CI calls no models and is not presented as a new
live run.

## Screenshots, sources and logs

- [The JEVIS start screen](../screenshots/jevis-start-screen.svg), with the stages
  explained, a permanent log panel on the right and the mode switch at the bottom.
- [A question](../screenshots/guided-questions-browser.png) / [SVG](../screenshots/guided-questions.svg).
- [The review of the chosen answer](../screenshots/guided-answers.svg).
- [The plan after the resume](../screenshots/guided-plan-browser.png) / [SVG](../screenshots/guided-plan.svg).
- [The result](../screenshots/guided-result-browser.png) / [SVG](../screenshots/guided-result.svg).
- [The graph and the actual Jev answer](../screenshots/guided-jev-browser.png) / [SVG](../screenshots/guided-jev.svg).
- [Live run summary](./live-summary.json), [the full portable session](./live-session/).
- Terminal recordings: [the discussion](./terminal-live.ansi.gz) and [the execution](./terminal-execution.ansi.gz).
  This is gzipped ANSI, including interface redraws, with no video timeline.

In the published text logs the author's checkout root is replaced with
`<checkout>`. The calculator code is saved byte for byte; the workspace path of
the portable session is resolved through `workspace_relative`. No API keys are
included.

The separate images in `../intake-ui/` are interface tests with prepared answers,
as stated in their README. They cannot be used as evidence of the API.

During verification we fixed the relative `--resume` path, cancellation before
the start, and keeping a long answer when the task fails to compile. The adapted
code from OpenCode, Hermes and Codex, the licences and the pinned versions are
described in [ATTRIBUTION.md](../../research/ATTRIBUTION.md). The test suites of
those upstream projects were not run here.

This run shows a reproducible path from an ambiguous sentence to a useful tool.
One request does not measure the quality of the questioning on arbitrary tasks,
speed relative to other agents, or Jev's overall contribution to code quality.
