# Real Codex worker: three toy repairs

Selector: `jev`.

Live Jev diagnostic routing and shadow annotations with a real Codex worker. Three authored toy faults, one run each; no superiority or general reliability claim.

## ui-title-only

- Harness: **complete** (acceptance_contract_satisfied).
- Worker corrections: 1. Executed checks: 5.
- Selected diagnostics: D2; event-log status: readable.
- Judge invocations: 3. Remote Jev requests: 3.
- Jev usage: `{"input_tokens": 2115, "output_tokens": 109}`; completeness: `True`; judge latency: 2849.78 ms.
- Post-stop independent acceptance: **True**. False complete: **False**.
- Wall time including final oracle: 20.98 seconds.

## backend-title-only

- Harness: **stop** (no_supported_diagnostic).
- Worker corrections: 0. Executed checks: 2.
- Selected diagnostics: none recorded; event-log status: readable.
- Judge invocations: 2. Remote Jev requests: 2.
- Jev usage: `{"input_tokens": 1575, "output_tokens": 69}`; completeness: `True`; judge latency: 1932.99 ms.
- Post-stop independent acceptance: **False**. False complete: **False**.
- Wall time including final oracle: 2.17 seconds.

## both-title-only

- Harness: **complete** (acceptance_contract_satisfied).
- Worker corrections: 1. Executed checks: 5.
- Selected diagnostics: D2; event-log status: readable.
- Judge invocations: 3. Remote Jev requests: 3.
- Jev usage: `{"input_tokens": 2108, "output_tokens": 109}`; completeness: `True`; judge latency: 2804.21 ms.
- Post-stop independent acceptance: **True**. False complete: **False**.
- Wall time including final oracle: 21.57 seconds.
