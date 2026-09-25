# Crypto Ledger: a practice project with defects

Synthetic trades; no external APIs, exchange keys or real money are needed.
The agent's task is to fix `ledger.py` and keep the `analyze(rows)` interface and the CLI.

```bash
python3 cryptoledger.py examples/trades.csv --json report.json
python3 -m unittest discover -s tests -v
```

CSV: `trade_id,timestamp,symbol,side,quantity,price_usdt,fee_usdt`.
The timestamp must carry a timezone. `side` is `buy` or `sell`, case-insensitive;
the symbol is normalised to upper case, and the ID and the symbol are not empty. Quantity
and price are strictly positive, the fee is non-negative; every Decimal is finite.
The first valid row for an ID wins, even if an invalid row with the same ID came earlier.

JSON: `accepted_rows`, `duplicate_rows`, `rejected_rows`, `warnings`, `timeline`,
`symbols`. `timeline` needs `trade_id` and `timestamp` in ISO UTC with six microsecond
digits and `Z`; the order is UTC, then trade_id. Each symbol needs the Decimal strings
`net_quantity`, `net_cashflow_usdt`, `fees_usdt`; the scale of the string is arbitrary.
Buy: cashflow = −quantity×price−fee. Sell: +quantity×price−fee.
Every rejected row gets its own warning in `warnings`.
An empty input gives zero counters and an empty timeline, warnings and symbols.

This is **cashflow accounting**, not a realised PnL calculation and not a trading strategy.
The tests in `tests/` and `jev-checks.json` are fixed before the agent runs and must not be changed.
