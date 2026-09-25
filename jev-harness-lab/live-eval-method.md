# How the live Jev evaluations are built

`live_eval.py` checks narrow decisions against real TypeSafe answers. Each set holds 18 pre-labelled states: ten tickets in Russian and English with two questions each, and eight diagnostic cases with one. That makes 28 decisions per set. These are small examples we wrote ourselves, not a random sample from production.

## What is checked

For a ticket the model picks the category through Choice and answers through Noul whether the author described a workaround they used successfully. For a diagnostic it picks D1, D2 or `none_suitable` from the observations passed in: which fresh check would still add information, whether the application can be imported, and which checks have already run.

The evaluation itself does not execute the diagnostic and does not establish whether the observations passed in are true. It checks the decision against the text of the state. Score is shown in the article's separate first calls, but it is not part of these 28 decisions.

The primary set is [fixtures/live-eval-cases.json](./fixtures/live-eval-cases.json). The harder one is [fixtures/live-eval-challenge-cases.json](./fixtures/live-eval-challenge-cases.json): it adds negations, distracting words, untested or failed workarounds, stale results, and instructions hidden in the data. The second set was assembled separately, without reading the predictions of the first run, and it uses the same questions and thresholds.

## How the experiment's conditions are protected

Only `state`, the questions and the requested model are sent to the API. Expected answers, the language and the case ID are not added to state. Before the requests, the runner saves a copy and the SHA-256 of the set, a hash of the questions and of the client code, the thresholds, the endpoint, the model and the time. That is how later changes can be told apart from the conditions of the original run.

The model in the saved experiments is `jev-1.13.0`. The provider response is saved whole, including the model and the metadata it returned. If a fingerprint is absent, none is invented. Original results are not rewritten after a change to the client code.

A Choice is allowed to act at confidence ≥0.60. A Noul gives "no" at ≤0.20 and "yes" at ≥0.80; in between it declines to decide. For the separate raw accuracy metric, Noul is split at 0.5. The thresholds were set before the answers; they are not a calibrated guarantee about risk.

A confident `none_suitable` is a legitimate answer in its own right and can be the correct one. It is counted separately from declining out of low confidence. Raw accuracy uses only valid answers; coverage uses every expected answer, including the ones never received. The report carries the number of accepted wrong decisions: a high score among accepted decisions must not be presented as full coverage.

Simple baseline rules are pinned as well: category by keywords, workaround always false, diagnostic always D1. These are transparent weak reference points, not well-tuned competitors. They are computed over all 28 expected answers even when the API fails; compare them with the denominators in mind and with each question type taken separately.

## What came out on 20 September

In the [primary set](../verification/jev-live-2026-09-20/primary-eval/results.json): 18 valid API answers and 28/28 matches with the labels: category 10/10, workaround 10/10, diagnostic 8/8. The policy accepted all 28 decisions, and two `none_suitable` answers turned out to be correct.

In the [harder set](../verification/jev-live-2026-09-20/challenge-eval/results.json): the same 18 requests and 28/28 matches; every decision accepted, three correct `none_suitable`. Neither run had API errors or refusals on low confidence.

These results show how specific requests behave on specific examples. They do not measure production accuracy, the calibration of probabilities, general protection against instructions inside data, money saved, or any improvement to a coding agent. In the separate real loop of Jev plus Codex, one of the three cases did stop on insufficient confidence, and that must not be hidden behind the correct answers of these sets. [The article's full protocol](../VALIDATION.md) and [the gallery of source evidence](../verification/evidence-gallery.html).

## Reproducing this

From the `jev-harness-lab` directory:

```bash
python3 live_eval.py --out runs/my-jev-plan --dry-run
python3 live_eval.py --out runs/my-jev-primary
python3 live_eval.py --cases fixtures/live-eval-challenge-cases.json --out runs/my-jev-challenge
```

The last two commands need `TYPESAFE_API_KEY` in the environment. `--dry-run` saves the plan and the requests, does not call the API and creates no predictions. A missing key produces no answers either: the runner saves the status `credentials_required` and returns code 1. Existing `--out` directories are not overwritten.

Each live set is at most 18 sequential requests with no automatic retries. Each request has an overall deadline of no more than 30 seconds. The first API or protocol error stops the sending, and the remaining cases are counted as answers never received. The Authorization header and the key are not written into the saved files.

## What the results contain

- `results.json`: the actual answers, gold, the policy decisions, the metrics, usage and timings.
- `report.md`: a readable report over the same data.
- `dataset.json`, `protocol.json`, `requests/`: the conditions of the experiment as they stood before the answers.
- `judge/judge-NNN.json`: the request and the unmodified JSON answer, or the error; successful answers are also written under the case ID.

Request duration includes the network. Tokens are not converted into money without a rate. In the current client, valid provider counters are recorded before `answers` is validated, so a rejected answer does not disappear from the known spend. `usage_complete=false` signals an error in a live request; `usage_reported_requests` and `usage_unreported_requests` show whether counters were present. Zero known tokens on an error does not mean the request cost nothing. Older saved protocols, written before these fields were added, stay as they were.

To check the whole chain once Codex is set up, there is a separate command:

```bash
python3 worker_eval.py --selector jev --out runs/my-jev-codex
```

It runs the three prepared defects and the independent acceptance after the stop. That is a different experiment: it executes code and spends Codex limits. [The route to your first run without keys](../START-HERE.md) helps you understand the mechanics first.

The runner's automated tests use explicitly injected clients and temporary directories. They check validation, the separation of gold from the request, the limits, a missing key, refusals and errors. Their passing does not add to the live Jev metrics.
