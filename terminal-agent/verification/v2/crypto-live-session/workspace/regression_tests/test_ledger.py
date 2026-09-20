"""Additional regressions; the pre-existing tests/ contract is untouched."""

import csv
from decimal import Decimal, localcontext
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ledger import CSV_FIELDS, analyze


ROOT = Path(__file__).resolve().parents[1]


def trade(identity="a", **changes):
    result = dict(trade_id=identity, timestamp="2026-09-20T09:00:00Z", symbol="BTC",
                  side="buy", quantity="0.1", price_usdt="0.2", fee_usdt="0.001")
    result.update(changes)
    return result


class LedgerRegressions(unittest.TestCase):
    def test_every_numeric_field_rejects_nonfinite_and_invalid_values(self):
        invalid = ["NaN", "sNaN", "Infinity", "-Infinity", "-0.01", "", "bad", None, True, 0.1]
        for field in ("quantity", "price_usdt", "fee_usdt"):
            for value in invalid:
                with self.subTest(field=field, value=value):
                    report = analyze([trade(**{field: value}), trade("good")])
                    self.assertEqual(report["rejected_rows"], 1)
                    self.assertEqual(report["accepted_rows"], 1)
                    self.assertEqual(len(report["warnings"]), 1)
        for field in ("quantity", "price_usdt"):
            for value in ("0", "-0"):
                with self.subTest(field=field, value=value):
                    self.assertEqual(analyze([trade(**{field: value})])["rejected_rows"], 1)

    def test_invalid_duplicate_is_rejected_and_does_not_change_totals(self):
        rows = [trade(quantity="bad"), trade(), trade(fee_usdt="NaN"), trade(quantity="100")]
        report = analyze(iter(rows))
        self.assertEqual((report["accepted_rows"], report["duplicate_rows"], report["rejected_rows"]),
                         (1, 1, 2))
        self.assertEqual(report["symbols"], analyze([trade()])["symbols"])
        self.assertEqual(len(report["warnings"]), 2)

    def test_first_valid_means_input_order_before_timestamp_sorting(self):
        report = analyze([trade(" same ", symbol=" btc ", side=" BUY "),
                          trade("same", timestamp="2020-01-01T00:00:00Z", symbol="ETH")])
        self.assertEqual(report["duplicate_rows"], 1)
        self.assertEqual(set(report["symbols"]), {"BTC"})
        self.assertEqual(report["timeline"], [
            {"trade_id": "same", "timestamp": "2026-09-20T09:00:00.000000Z"}])

    def test_fractional_utc_time_crosses_day_boundary(self):
        report = analyze([trade("b", timestamp="2026-01-01T00:00:00.123456+01:00"),
                          trade("a", timestamp="2025-12-31T23:00:00.123456Z"),
                          trade("earlier", timestamp="2025-12-31T23:00:00.123455Z")])
        self.assertEqual([item["trade_id"] for item in report["timeline"]], ["earlier", "a", "b"])
        self.assertEqual(report["timeline"][2]["timestamp"], "2025-12-31T23:00:00.123456Z")
        bad_dates = ("2026-02-30T00:00:00Z", "2026-09-20", "0001-01-01T00:00:00+01:00")
        self.assertEqual(analyze([trade(str(i), timestamp=t) for i, t in enumerate(bad_dates)])
                         ["rejected_rows"], len(bad_dates))

    def test_decimal_precision_is_exact_and_context_is_preserved(self):
        with localcontext() as context:
            context.prec = 3
            report = analyze([
                trade(quantity="123456789012345678901234567890.123456789", price_usdt="3",
                      fee_usdt="0.000000001"),
                trade("sell", side="sell", quantity="0.123456789", price_usdt="1",
                      fee_usdt="0.000000002"),
            ])
            self.assertEqual(context.prec, 3)
        bucket = report["symbols"]["BTC"]
        self.assertEqual(Decimal(bucket["net_quantity"]), Decimal("123456789012345678901234567890"))
        self.assertEqual(Decimal(bucket["net_cashflow_usdt"]),
                         Decimal("-370370367037037036703703703670.246913581"))
        self.assertEqual(Decimal(bucket["fees_usdt"]), Decimal("0.000000003"))

    def test_sell_without_opening_balance_and_fee_above_proceeds(self):
        report = analyze([trade(side="SELL", quantity="2", price_usdt="3", fee_usdt="7")])
        self.assertEqual({k: Decimal(v) for k, v in report["symbols"]["BTC"].items()},
                         {"net_quantity": Decimal("-2"), "net_cashflow_usdt": Decimal("-1"),
                          "fees_usdt": Decimal("7")})
        self.assertEqual(analyze([trade(fee_usdt="-0")])["accepted_rows"], 1)

    def test_bad_shapes_are_rejected_without_stopping_iteration(self):
        rows = [None, [], {}, trade(symbol=None), trade(trade_id=42)]
        for field in CSV_FIELDS:
            incomplete = trade()
            del incomplete[field]
            rows.append(incomplete)
        extra = trade()
        extra[None] = ["extra"]
        rows.append(extra)
        report = analyze(rows + [trade("good")])
        self.assertEqual(report["rejected_rows"], len(rows))
        self.assertEqual(len(report["warnings"]), len(rows))
        self.assertEqual(report["accepted_rows"], 1)


class CLIRegressions(unittest.TestCase):
    def run_cli(self, source, output):
        return subprocess.run([sys.executable, "-B", str(ROOT / "cryptoledger.py"), str(source),
                               "--json", str(output)], capture_output=True, text=True, timeout=8)

    def test_csv_bom_short_extra_and_broken_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.csv"
            output = Path(tmp) / "nested" / "report.json"
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerow(trade("first"))
            buffer.write('broken,"oops"x,BTC,buy,1,2,0\n')
            buffer.write('short,2026-09-20T09:00:00Z,BTC,buy,1\n')
            buffer.write('extra,2026-09-20T09:00:00Z,BTC,buy,1,2,0,unexpected\n')
            writer.writerow(trade("last", side="sell"))
            source.write_text(buffer.getvalue(), encoding="utf-8-sig")
            result = self.run_cli(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual((report["accepted_rows"], report["duplicate_rows"], report["rejected_rows"]),
                             (2, 0, 3))
            self.assertEqual(len(report["warnings"]), 3)
            self.assertEqual(result.stderr.count("Предупреждение:"), 3)
            self.assertEqual(Decimal(report["symbols"]["BTC"]["net_cashflow_usdt"]), Decimal("-0.002"))

    def test_empty_file_and_header_only_produce_empty_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.csv"
            output = Path(tmp) / "report.json"
            for content in ("", ",".join(CSV_FIELDS) + "\n"):
                with self.subTest(content=content):
                    source.write_text(content, encoding="utf-8")
                    result = self.run_cli(source, output)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(output.read_text(encoding="utf-8")), analyze([]))

    def test_invalid_headers_and_missing_file_fail_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.csv"
            output = Path(tmp) / "report.json"
            contents = [None, "wrong,columns\n", ",".join(CSV_FIELDS[:-1] + ("quantity",)) + "\n"]
            for content in contents:
                with self.subTest(content=content):
                    if content is not None:
                        source.write_text(content, encoding="utf-8")
                    result = self.run_cli(source, output)
                    self.assertEqual(result.returncode, 2)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertFalse(output.exists())

    def test_output_failure_has_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli(ROOT / "examples" / "trades.csv", Path(tmp))
            self.assertEqual(result.returncode, 2)
            self.assertIn("Ошибка записи", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_input_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.csv"
            content = ",".join(CSV_FIELDS) + "\n"
            source.write_text(content, encoding="utf-8")
            result = self.run_cli(source, source)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
