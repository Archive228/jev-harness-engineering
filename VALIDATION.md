# Check results · 20 September 2026

Three questions are kept apart here: whether the harness code works correctly, which decisions live Jev returned, and whether the whole chain managed to repair the application. The source records and terminal logs are in the [evidence gallery](./verification/evidence-gallery.en.html). For running it yourself there is a [10-minute route](./START-HERE.md).

## Automated checks

**83 tests pass** on macOS / Python 3.9.6. unittest output: [unit-tests-83.txt](./verification/terminal/unit-tests-83.txt), metadata: [local-tests-2026-09-20.json](./verification/local-tests-2026-09-20.json). unittest itself reported 4.956 seconds; the 5.019 seconds in the metadata include process startup.

```bash
cd jev-harness-lab
python3 -B -m unittest discover -s tests -v
```

The regression tests cover the application exiting early before a check completes; a change to the code or the contract; stale records; moving saved state along with the project; an incomplete acceptance report; unknown and corrupted Choice options; API errors; timeouts and limits; worker child processes; credential passing; the independent oracle and stopping replay at the first divergence.

Also checked: a failure of the optional Noul annotation does not block a working project; an error from the real Choice router still stops the loop; the global limit is not ignored. Valid API counters are stored even when answers are invalid, and missing usage is marked explicitly. These tests use a controlled transport; live results from the service are given separately below.

## The first two requests: one ticket, different wordings

`run.py inspect` sent one live request with the ticket text in Russian and the questions in English: Choice=`export`, Score=`1.0`, Noul=`0.89`. [Answer and request](./verification/jev-live-2026-09-20/inspect/judge/judge-001.json), [run result](./verification/jev-live-2026-09-20/inspect/result.json).

A standalone `first_call.py` was run separately with the Russian questions from the article: Choice=`export`, Score=`1.0`, Noul=`0.95`. [Request](./verification/jev-live-2026-09-20/first-call-ru/request.json), [full answer](./verification/jev-live-2026-09-20/first-call-ru/response.json), [metadata](./verification/jev-live-2026-09-20/first-call-ru/metadata.json). The numbers apply to these particular wordings and runs. Repeatability of a single Noul to the last digit was not tested.

## Live checks of Jev's decisions

The model in both sets is `jev-1.13.0`. Each has 18 states: ten RU/EN tickets with two questions and eight diagnostic cases with one question. 28 decisions in each. Reference labels were not passed to the model, and no question or threshold was changed in response to the answers.

- **Primary set:** 18 requests, 28/28 correct decisions, 28 accepted by the policy, zero errors and zero low-confidence refusals. By type: category 10/10, workaround 10/10, next_check 8/8. Two `none_suitable` answers matched the labels. [Report](./verification/jev-live-2026-09-20/primary-eval/report.md), [JSON](./verification/jev-live-2026-09-20/primary-eval/results.json).
- **Separate harder set:** 18 requests, 28/28 correct decisions, 28 accepted by the policy, zero errors and zero low-confidence refusals. By type again 10/10, 10/10 and 8/8, with three correct `none_suitable`. It includes negations, distracting titles, unverified workarounds, stale observations and attempts to force an answer from inside the data. [Report](./verification/jev-live-2026-09-20/challenge-eval/report.md), [JSON](./verification/jev-live-2026-09-20/challenge-eval/results.json).

The second set kept the earlier questions and thresholds. Its cases were prepared separately, without reading the first run's predictions. Both sets were written by the authors and are small: 56 matches against the labels do not establish production accuracy, confidence calibration, robustness to every prompt injection, or an advantage over a good deterministic rule. Score is shown separately in the first requests, but these two matrices assess Choice and Noul.

Recorded usage for the primary set: 9,322 input and 1,024 output tokens; for the harder set: 10,824 and 1,026. The request durations sum to 17,102.64 and 17,261.21 ms respectively, network latency included. This is not model-only latency and not a monetary cost. [Full method](./jev-harness-lab/live-eval-method.md).

```bash
python3 live_eval.py --out runs/my-jev-primary
python3 live_eval.py --cases fixtures/live-eval-challenge-cases.json --out runs/my-jev-challenge
```

## The whole chain: Jev chooses, Codex repairs

Three defects and the source hashes were frozen before the runs. Selector=`jev`, one run per defect. [Manifest](./verification/jev-live-2026-09-20/codex-matrix/manifest.json), [report](./verification/jev-live-2026-09-20/codex-matrix/evaluation.md), [all results](./verification/jev-live-2026-09-20/codex-matrix/evaluation.json).

- `ui-title-only`: `complete`, D2, one Codex repair, five checks, three Jev requests. Independent acceptance PASS. 20.98 s.
- `backend-title-only`: `stop`, two mandatory checks, two Jev requests, **the worker never ran**. Jev preferred D2 with probability 0.68 but returned confidence 0.52, below the 0.60 threshold. Stop reason `no_supported_diagnostic`. Independent acceptance confirmed the application was still broken. 2.17 s. [The actual Choice](./verification/jev-live-2026-09-20/codex-matrix/backend-title-only/judge/judge-002.json).
- `both-title-only`: `complete`, D2, one Codex repair, five checks, three Jev requests. Independent acceptance PASS. 21.57 s.

The first route ends with **two completions out of three**, one stop, zero false `complete`. The times include the whole run and the extra oracle. Confidence 0.52 must not be swapped for the chosen option's probability of 0.68: the policy checks the first field.

### Explicit recovery after the stop

The `backend-title-only` state was copied into a separate folder, then `selector=all` was set. The program ran both diagnostics, Codex made one repair, and fresh C1/C2 passed. This continuation has four new checks, zero Jev requests and independent acceptance PASS, 14.80 s including the oracle. The two earlier mandatory results were already in the saved state.

This is a separate action after the original stop. It does not turn the first route into "3/3" and does not mean there is a hidden automatic fallback. [Switch log](./verification/jev-live-2026-09-20/backend-recovery/protocol.json), [result and independent acceptance](./verification/jev-live-2026-09-20/backend-recovery/recovery.json).

```bash
python3 adapters/codex_cli.py --configure
python3 worker_eval.py --selector jev --out runs/my-jev-codex
```

## The earlier standalone Codex run · 19 September

Selector=`fixed`, real Jev requests **0**. `ui-title-only`, `backend-title-only` and `both-title-only` each finished after one repair and five checks, with independent acceptance PASS. Times: 15.17 / 17.02 / 20.43 s. Codex CLI `0.155.0-alpha.9` was used, with ChatGPT authorisation and the currently configured model, no override.

This historical run is kept: [evaluation.md](./verification/codex-worker-2026-09-19/evaluation.md), [evaluation.json](./verification/codex-worker-2026-09-19/evaluation.json), [manifest.json](./verification/codex-worker-2026-09-19/manifest.json). It checks the worker plus harness chain without Jev. Single timings must not be compared as evidence of a speed-up or a slow-down.

## Acceptance, failures and accounting

C1 and C2 determine whether the two declared requirements are met. The extra oracle after the stop runs four other search queries in a separate process with a cleaned environment, and its results are not passed to the worker. Neither the two acceptance tests nor the four extra queries cover every possible application error.

A Noul assesses in text how a test's scope relates to the requirement and stays an optional annotation. An error from its API is recorded as `scope_annotation_error` but does not cancel checks that passed. An error from the Choice router stops further selection. The time and call-count limits hold in both cases.

The current client records verified provider usage before validating `answers`. `usage_complete=false` marks a failed live request. `usage_reported_requests` and `usage_unreported_requests` show how many requests returned complete counters and how many did not. The sum of known tokens is not presented as the full cost. These fields were added after the first standalone requests and the primary eval, and their original JSON files were not rewritten. Results contain hashes of the code used wherever the protocol calls for it.

## Offline matrix, CI and reproducibility

Nine `evaluate.py` runs, three prepared cases × fixed/all/jev: six `complete`, three expected stops with no progress, no false completions. The checks really execute, but the demo Jev answers and the worker repairs are synthetic. [Saved matrix](./jev-harness-lab/evaluation-example/evaluation.json).

[GitHub Actions passed](https://github.com/Archive228/jev-harness-engineering/actions/runs/35505100114) on commit `1d8f11880751bb432a0533280818e77c612e9adb`: **83 tests and the offline matrix on Python 3.9, 3.12, 3.13 and 3.14**, plus a separate HTML build that checks the result matches the published file. All five jobs succeeded. [CI metadata](./verification/ci-2026-09-20.json) and [the full command output](./verification/terminal/github-actions-2026-09-20.txt) are kept with the material. Adding this record afterwards does not change the code that was checked.

The HTML is built from Markdown with `npm ci --ignore-scripts` and `npm run build:article`. Node >=20, and the `marked` dependency is pinned. The repository is private: a reader without access needs the archive shipped with the material. API keys and local configs are excluded from Git. In the distributed logs the author's absolute path is replaced with `<workspace>`, while the actual answers and source hashes are kept.
