"""Offline cashflow and quantity accounting; no PnL or market valuation."""

from collections.abc import Mapping
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, MAX_EMAX, MIN_EMIN, localcontext


CSV_FIELDS = ("trade_id", "timestamp", "symbol", "side", "quantity", "price_usdt", "fee_usdt")


@dataclass(frozen=True)
class _Trade:
    trade_id: str
    timestamp: datetime
    symbol: str
    side: str
    quantity: Decimal
    price_usdt: Decimal
    fee_usdt: Decimal


def _text(row, field):
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: требуется непустая строка")
    return value.strip()


def _number(row, field, *, allow_zero=False):
    value = row.get(field)
    # Never convert binary floating-point inputs into accounting amounts.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError(f"{field}: требуется десятичное число без float")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field}: некорректное десятичное число") from None
    if not number.is_finite():
        raise ValueError(f"{field}: число должно быть конечным")
    if number < 0 or (not allow_zero and number == 0):
        requirement = "неотрицательным" if allow_zero else "строго положительным"
        raise ValueError(f"{field}: число должно быть {requirement}")
    return number


def _parse(row):
    if isinstance(row, csv.Error):
        raise ValueError(f"некорректный CSV: {row}")
    if not isinstance(row, Mapping):
        raise ValueError("ожидалась строка с полями CSV")
    if None in row:
        raise ValueError("лишние значения в строке CSV")
    trade_id = _text(row, "trade_id")
    symbol = _text(row, "symbol").upper()
    side = _text(row, "side").lower()
    if side not in ("buy", "sell"):
        raise ValueError("side: допустимы только buy и sell")
    timestamp = _text(row, "timestamp")
    # Python 3.9's fromisoformat does not recognize the UTC 'Z' suffix.
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(timestamp)
        if moment.utcoffset() is None:
            raise ValueError("missing timezone")
        moment = moment.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("timestamp: требуется корректная ISO-дата с часовым поясом") from None
    return _Trade(trade_id, moment, symbol, side, _number(row, "quantity"),
                  _number(row, "price_usdt"), _number(row, "fee_usdt", allow_zero=True))


def _add_exact(left, right):
    # Cover every decimal place of both operands, plus a possible carry.
    exponent = min(left.as_tuple().exponent, right.as_tuple().exponent)
    with localcontext() as context:
        context.prec = max(1, max(left.adjusted(), right.adjusted()) - exponent + 2)
        context.Emax, context.Emin = MAX_EMAX, MIN_EMIN
        return left + right


def _multiply_exact(left, right):
    with localcontext() as context:
        context.prec = len(left.as_tuple().digits) + len(right.as_tuple().digits)
        context.Emax, context.Emin = MAX_EMAX, MIN_EMIN
        return left * right


def analyze(rows):
    """Analyze mappings (or csv.Error markers); first valid trade_id wins."""
    report = {"accepted_rows": 0, "duplicate_rows": 0, "rejected_rows": 0,
              "warnings": [], "timeline": [], "symbols": {}}
    seen = set()
    trades = []
    for row_number, row in enumerate(rows, start=1):
        try:
            trade = _parse(row)
        except ValueError as error:
            report["rejected_rows"] += 1
            report["warnings"].append(f"Строка данных {row_number}: {error}")
            continue
        # Validate before deduplication: an invalid repeated ID is rejected.
        if trade.trade_id in seen:
            report["duplicate_rows"] += 1
            continue
        seen.add(trade.trade_id)
        trades.append(trade)
        report["accepted_rows"] += 1
        bucket = report["symbols"].setdefault(trade.symbol, {
            "net_quantity": Decimal(0), "net_cashflow_usdt": Decimal(0), "fees_usdt": Decimal(0)})
        quantity = trade.quantity
        cashflow = _multiply_exact(quantity, trade.price_usdt)
        if trade.side == "buy":
            cashflow = cashflow.copy_negate()
        else:
            quantity = quantity.copy_negate()
        cashflow = _add_exact(cashflow, trade.fee_usdt.copy_negate())
        bucket["net_quantity"] = _add_exact(bucket["net_quantity"], quantity)
        bucket["net_cashflow_usdt"] = _add_exact(bucket["net_cashflow_usdt"], cashflow)
        bucket["fees_usdt"] = _add_exact(bucket["fees_usdt"], trade.fee_usdt)
    report["timeline"] = [
        {"trade_id": trade.trade_id,
         "timestamp": trade.timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")}
        for trade in sorted(trades, key=lambda trade: (trade.timestamp, trade.trade_id))
    ]
    for bucket in report["symbols"].values():
        for key, value in bucket.items():
            bucket[key] = str(value)
    return report
