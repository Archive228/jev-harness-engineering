"""Контрольные расчёты и проверки настоящего терминального запуска."""

from decimal import Decimal
from pathlib import Path
import subprocess
import sys
import unittest

from crypto_profit import calculate_trade


SCRIPT = Path(__file__).with_name("crypto_profit.py")


class CalculationTests(unittest.TestCase):
    def test_without_fees(self):
        result = calculate_trade(Decimal("100"), Decimal("2"), Decimal("120"))
        self.assertEqual(result.purchase_cost, Decimal("200"))
        self.assertEqual(result.sale_proceeds, Decimal("240"))
        self.assertEqual(result.total_fees, Decimal("0"))
        self.assertEqual(result.profit, Decimal("40"))
        self.assertEqual(result.return_percent, Decimal("20"))

    def test_one_percent_on_both_operations(self):
        result = calculate_trade(
            Decimal("100"), Decimal("2"), Decimal("120"), Decimal("1"), Decimal("1")
        )
        self.assertEqual(result.purchase_cost, Decimal("202"))
        self.assertEqual(result.sale_proceeds, Decimal("237.60"))
        self.assertEqual(result.total_fees, Decimal("4.40"))
        self.assertEqual(result.profit, Decimal("35.60"))
        self.assertEqual(result.return_percent.quantize(Decimal("0.01")), Decimal("17.62"))

    def test_loss_break_even_and_total_loss(self):
        for sell_price, profit, percent in [(80, -40, -20), (100, 0, 0), (0, -200, -100)]:
            with self.subTest(sell_price=sell_price):
                result = calculate_trade(Decimal("100"), Decimal("2"), Decimal(sell_price))
                self.assertEqual(result.profit, Decimal(profit))
                self.assertEqual(result.return_percent, Decimal(percent))

    def test_different_fees_and_fractional_quantity(self):
        result = calculate_trade(
            Decimal("100"), Decimal("0.25"), Decimal("120"), Decimal("2"), Decimal("0.5")
        )
        self.assertEqual(result.purchase_cost, Decimal("25.50"))
        self.assertEqual(result.sale_proceeds, Decimal("29.85"))
        self.assertEqual(result.total_fees, Decimal("0.65"))
        self.assertEqual(result.profit, Decimal("4.35"))


class TerminalTests(unittest.TestCase):
    def run_calculator(self, lines):
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input="\n".join(lines) + "\n",
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_default_fees(self):
        process = self.run_calculator(["100", "2", "120", "", ""])
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Чистая прибыль / убыток: 40,00", process.stdout)
        self.assertIn("Доходность относительно затрат: 20,00%", process.stdout)
        self.assertEqual(process.stderr, "")

    def test_comma_and_independent_fees(self):
        process = self.run_calculator(["100", "0,25", "120", "2", "0,5"])
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("Общая комиссия: 0,65", process.stdout)
        self.assertIn("Чистая прибыль / убыток: 4,35", process.stdout)

    def test_invalid_input_retries_each_field(self):
        invalid_by_field = [
            ["abc", "", "0", "-1", "NaN", "Infinity"],
            ["abc", "", "0", "-1", "NaN", "Infinity"],
            ["abc", "", "-1", "NaN", "Infinity"],
            ["abc", "-1", "100", "101", "NaN", "Infinity"],
            ["abc", "-1", "100", "101", "NaN", "Infinity"],
        ]
        for field_index, invalid_values in enumerate(invalid_by_field):
            for invalid in invalid_values:
                with self.subTest(field=field_index, invalid=invalid):
                    lines = ["100", "2", "120", "0", "0"]
                    lines.insert(field_index, invalid)
                    process = self.run_calculator(lines)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    self.assertEqual(process.stdout.count("Ошибка:"), 1)
                    self.assertIn("Чистая прибыль / убыток: 40,00", process.stdout)
                    self.assertEqual(process.stderr, "")

    def test_fee_just_below_one_hundred_is_allowed(self):
        process = self.run_calculator(["100", "2", "120", "99,99", "99,99"])
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertNotIn("Ошибка:", process.stdout)

    def test_end_of_input_cancels_cleanly(self):
        process = self.run_calculator(["100"])
        self.assertEqual(process.returncode, 1)
        self.assertIn("Расчёт отменён: ввод прерван.", process.stdout)
        self.assertEqual(process.stderr, "")


if __name__ == "__main__":
    unittest.main()
