# Crypto Ledger — учебный проект с дефектами

Синтетические сделки; внешние API, ключи бирж и реальные деньги не нужны.
Задача агента — исправить `ledger.py`, сохранить интерфейс `analyze(rows)` и CLI.

```bash
python3 cryptoledger.py examples/trades.csv --json report.json
python3 -m unittest discover -s tests -v
```

CSV: `trade_id,timestamp,symbol,side,quantity,price_usdt,fee_usdt`.
Время обязано содержать timezone. `side` равен `buy` или `sell` без учёта регистра;
символ нормализуется в верхний регистр, ID и символ не пусты. Количество и цена
строго положительны, комиссия неотрицательна; все Decimal конечны.
Первая валидная строка ID побеждает, даже если раньше была невалидная с тем же ID.

JSON: `accepted_rows`, `duplicate_rows`, `rejected_rows`, `warnings`, `timeline`,
`symbols`. В `timeline` нужны `trade_id` и `timestamp` в ISO UTC с шестью цифрами
микросекунд и `Z`; порядок — UTC, затем trade_id. Для каждого символа нужны строки
Decimal `net_quantity`, `net_cashflow_usdt`, `fees_usdt`; масштаб строки произволен.
Покупка: cashflow = −quantity×price−fee. Продажа: +quantity×price−fee.
Для каждой отклонённой строки — отдельное предупреждение в `warnings`.
Пустой вход даёт нулевые счётчики, пустые timeline, warnings и symbols.

Это **учёт денежных потоков**, не расчёт реализованного PnL и не торговая стратегия.
Тесты в `tests/` и `jev-checks.json` заданы до запуска агента и менять их нельзя.
