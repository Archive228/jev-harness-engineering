# Small live Jev evaluation protocol

This runner measures narrow decisions from actual TypeSafe API responses. Its 18 manually authored examples were frozen before a live run and have not been used to tune the questions or thresholds from returned predictions. They are a small authored holdout, not a random or representative production benchmark. A successful run does not establish end-to-end agent improvement.

There are 10 English/Russian support tickets, each with a category Choice and an explicit successful-workaround Noul question, and 8 search-diagnostic cases with D1, D2 or `none_suitable`. Diagnostic gold is grounded in the supplied observations: which fresh check remains informative, whether tests can import the application, and whether both checks already ran. These cases evaluate supplied-state reasoning; they do not execute the diagnostic or independently establish that supplied observations are true.

`fixtures/live-eval-cases.json` holds the input and expected labels. Only each case's `state`, frozen questions, and requested model enter the API payload. Expected labels, language, and case metadata are withheld. The output includes a copy and SHA-256 of the dataset, question hash, runner hash, policy thresholds, endpoint, model, and timestamp so later edits are visible. If the provider returns a model identifier, version or fingerprint, it is retained. No absent fingerprint is invented.

Choice accepts confidence ≥0.60. Noul accepts “no” at ≤0.20 and “yes” at ≥0.80; the middle band abstains. These thresholds are illustrative preregistered policy values, not calibrated risk guarantees. For raw accuracy only, Noul uses 0.5. A confident `none_suitable` is a potentially correct decision and is counted separately from uncertainty abstention. Raw accuracy uses valid answers; coverage uses all expected answers, including unanswered ones. Accepted accuracy and accepted incorrect decisions are both reported, so abstention cannot masquerade as full coverage.

Controls are deliberately simple and frozen: support category uses literal keyword matching, workaround always predicts false, diagnostic always selects D1. They are not tuned, competitive baselines. Their labels are evaluated on all 28 expected answers even if the API run fails. Read per-question counts; one combined score would mix three different decisions and denominators.

```bash
python3 live_eval.py --out runs/live-eval-plan --dry-run
# With TYPESAFE_API_KEY present in the environment:
python3 live_eval.py --out runs/live-eval-real
```

A dry run saves protocol and request payloads but produces no Jev answers and makes zero API requests. Missing credentials likewise produces no predictions and exits with status 1. A live run makes at most 18 sequential requests, with no automatic retries and a total deadline of at most 30 seconds for each request. The first API/protocol failure stops further requests and remains in the report; skipped cases remain unanswered. Existing output directories are never overwritten. Authorization headers and keys are not written to artifacts.

`results.json` contains actual answer-level predictions, expected labels, decisions, metrics, provider usage and elapsed times. `report.md` renders those values. `judge/judge-NNN.json` preserves the raw request/response or transport error through the shared client; each successful response is also stored by case ID. Network overhead is included in latency. No dollar estimate is made from tokens alone, and no generated model explanation is asserted.

The runner's unit tests use explicitly mocked clients and temporary directories. Passing those tests establishes the evaluation plumbing, request/gold separation, bounds, no-credentials behavior, abstention accounting and error behavior; it is never counted as live model accuracy.
