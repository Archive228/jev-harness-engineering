# Small live Jev evaluation

Mode: **live**. Status: **completed**.

This is an authored, preregistered 18-case check of the API and narrow decisions; it is not a representative benchmark or an estimate of production reliability.

Requested model: `jev-1.13.0`. Dataset SHA-256: `57179107cd4df9a3511d290583f16b5cc60dc8c9cba7a653863bf32ccd1a3ecf`.

Actual remote requests: 18. Valid responses: 18. Errors: 0.

Raw labels correct: **28 / 28 valid answers** (28 expected answers, 0 unanswered).

Policy: 28 accepted decisions, 28 correct, 0 incorrect; 0 confidence/uncertainty abstentions. Coverage: 1.0. Explicit `none_suitable`: 3.

- `category`: raw 10/10; accepted 10/10; uncertainty abstentions 0; unanswered 0.
- `has_workaround`: raw 10/10; accepted 10/10; uncertainty abstentions 0; unanswered 0.
- `next_check`: raw 8/8; accepted 8/8; uncertainty abstentions 0; unanswered 0.

Reported API tokens: 10824 input, 1026 output. Sum of request durations: 17261.21 ms. These durations include network overhead and are not model-only latency.

Usage complete: **True**. Remote requests with validated counters: 18; without counters: 0. Totals include only reported counters; zero is not evidence that an unsuccessful request was free.

## Fixed local controls

Category: fixed keyword rules; workaround: always false; diagnostic: always D1. These weak controls are transparent reference points, not tuned competitive baselines.

- `category`: 4/10.
- `has_workaround`: 5/10.
- `next_check`: 3/8.

## Interpretation

Questions and labels were frozen before this run. No threshold is fitted to these cases: Choice confidence ≥0.60 is accepted; Noul ≤0.20 means no, ≥0.80 means yes, and the middle band abstains. Raw Noul labels use 0.5 only for reporting raw accuracy. `none_suitable` is an explicit potentially correct decision, counted separately from uncertainty abstention.

No worker is run here. These results do not establish end-to-end repair quality, monetary savings, or superiority over a well-designed deterministic router. Each request and unmodified provider response is recorded separately; no provider explanation is invented.
