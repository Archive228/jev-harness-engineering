"""Contract authored before the live agent run. Fixed known accounting examples."""
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ledger import analyze


def row(identity="a", **changes):
    value = dict(trade_id=identity, timestamp="2026-09-20T09:00:00Z", symbol="BTC", side="buy",
                 quantity="0.1", price_usdt="0.2", fee_usdt="0.001")
    value.update(changes)
    return value


class LedgerContract(unittest.TestCase):
    def test_decimal_cashflow_includes_fees(self):
        result = analyze([row(), row("b", side="sell", quantity="0.04", price_usdt="0.3", fee_usdt="0.002")])
        btc = result["symbols"]["BTC"]
        self.assertEqual(Decimal(btc["net_quantity"]), Decimal("0.06"))
        self.assertEqual(Decimal(btc["net_cashflow_usdt"]), Decimal("-0.011"))
        self.assertEqual(Decimal(btc["fees_usdt"]), Decimal("0.003"))

    def test_first_valid_id_wins(self):
        result = analyze([row(quantity="-1"), row(), row(quantity="9")])
        self.assertEqual((result["accepted_rows"], result["rejected_rows"], result["duplicate_rows"]), (1, 1, 1))
        self.assertEqual(Decimal(result["symbols"]["BTC"]["net_quantity"]), Decimal("0.1"))

    def test_utc_order_and_ties(self):
        result = analyze([row("z", timestamp="2026-09-20T10:00:00+01:00"),
                          row("late", timestamp="2026-09-20T05:30:00-04:00"),
                          row("a", timestamp="2026-09-20T12:00:00+03:00")])
        self.assertEqual([r["trade_id"] for r in result["timeline"]], ["a", "z", "late"])
        self.assertEqual(result["timeline"][0]["timestamp"], "2026-09-20T09:00:00.000000Z")

    def test_invalid_numbers_dates_and_shape(self):
        bad = [row(str(i), **changes) for i, changes in enumerate([
            {"quantity": "NaN"}, {"quantity": "Infinity"}, {"quantity": "0"}, {"price_usdt": "-1"},
            {"fee_usdt": "-1"}, {"side": "stake"}, {"timestamp": "2026-09-20T09:00:00"},
            {"timestamp": "bad"}, {"symbol": " "}, {"trade_id": ""}])]
        result = analyze(bad + [{}, row("good")])
        self.assertEqual(result["rejected_rows"], 11)
        self.assertEqual(len(result["warnings"]), 11)
        self.assertEqual(result["accepted_rows"], 1)

    def test_symbols_stay_separate_and_normalized(self):
        result = analyze([row(symbol="btc", side="BUY"), row("eth", symbol="ETH", quantity="2", price_usdt="3", fee_usdt="0")])
        self.assertEqual(set(result["symbols"]), {"BTC", "ETH"})
        self.assertEqual(Decimal(result["symbols"]["ETH"]["net_cashflow_usdt"]), Decimal("-6"))
        self.assertEqual(Decimal(result["symbols"]["BTC"]["net_cashflow_usdt"]), Decimal("-0.021"))

    def test_empty(self):
        self.assertEqual(analyze([]), {"accepted_rows": 0, "duplicate_rows": 0, "rejected_rows": 0,
                                       "warnings": [], "timeline": [], "symbols": {}})

    def test_cli_synthetic_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "nested" / "report.json"
            result = subprocess.run([sys.executable, "-B", "cryptoledger.py", "examples/trades.csv", "--json", str(output)],
                                    text=True, capture_output=True, timeout=8)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual((report["accepted_rows"], report["duplicate_rows"], report["rejected_rows"]), (3, 1, 1))
            self.assertEqual(Decimal(report["symbols"]["BTC"]["net_cashflow_usdt"]), Decimal("-3524.24"))


if __name__ == "__main__":
    unittest.main()
