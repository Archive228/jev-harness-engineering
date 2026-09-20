# Independent verification of the live calculator

The live agent generated `crypto_profit.py`, its README and its own tests after
the questionnaire and explicit acceptance of the plan. A separate reviewer then
ran this black-box harness against that completed workspace. The harness does
not import calculator functions and does not calculate expectations with the
implementation under test. It starts the real documented CLI with supplied
input and checks exact result lines, errors, stderr and exit status.

Result on Python **3.9.6**: **47 of 47 independent CLI cases passed**.
The generated test suite was also rerun separately: **9 tests passed**. These
are separate counts; the agent's own tests are not presented as independent
acceptance evidence. SHA-256 hashes confirm the three workspace source files
were unchanged by the audit. Bytecode files are excluded from that comparison;
the audit sets `PYTHONDONTWRITEBYTECODE=1`.

Coverage:

- Eight valid calculations: explicit and default zero fees, the approved 1%
  fee example, loss, break-even, zero sale price, decimal-comma inputs with
  unequal fees, and a valid fee immediately below the 100% boundary.
- Thirty-four invalid-input cases across all five fields. Each must explain
  the error, repeat that field, consume a subsequent valid value, and finish
  with the unchanged expected calculation. These include strings, empty
  required values, NaN, positive/negative infinity, invalid negative values,
  zero purchase price/quantity, and commissions of 100% or above.
- Five EOF cases, one at each input boundary. Each must cancel with a clear
  message and exit 1 without a traceback or result.

The principal expected values come directly from the accepted plan:
2 × 100 bought and 2 × 120 sold gives 40.00 profit and 20.00% without fees;
1% on each side gives costs 202.00, net proceeds 237.60, fees 4.40,
profit 35.60 and a displayed return of 17.62%. An additional independently
chosen example buys 0.5 units at 80 and sells them at 100 with 2% and 1% fees:
costs 40.80, proceeds 49.50, fees 1.30, profit 8.70, return 21.32%.

Reproduce from `terminal-agent/` with the calculator workspace path:

```sh
python3 verification/guided/independent/check_cli.py /path/to/calculator/workspace
```

`results.json` contains every input, expected output, result, runtime and source
hash. `results.txt` is the short report. `cases/` contains the full stdin/stdout
record of every independent subprocess. `generated-tests.txt` records the
separate generated suite.

This is an **after-run audit**, not a pre-registered contract enforced during
that Jev run. It verifies these scenarios, not all possible numerical input.
No packages were installed for these checks; the CLI was launched using the
existing Python interpreter. This harness did not monitor operating-system
network traffic.
