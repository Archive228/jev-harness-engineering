"""Recommendation labels must never become the user's stored answer."""
import unittest

from jev_agent.choice_labels import mark_recommended, strip_recommended


class ChoiceLabelTests(unittest.TestCase):
    def test_decorating_does_not_mutate_or_alias_bare_values(self):
        choices = ["  Анализ CSV  ", "Отчёт"]
        shown = mark_recommended(choices)
        self.assertEqual(shown, ["Анализ CSV (Recommended)", "Отчёт"])
        self.assertEqual(choices, ["  Анализ CSV  ", "Отчёт"])
        shown[1] = "changed"
        self.assertEqual(choices[1], "Отчёт")

    def test_russian_and_english_labels_are_idempotent(self):
        for label in ("(Рекомендуется)", "(Recommended)", "(рекомендуется)", "(RECOMMENDED)"):
            with self.subTest(label=label):
                choices = ["CSV " + label, "JSON"]
                self.assertEqual(mark_recommended(choices), choices)
                self.assertEqual(strip_recommended(choices[0]), "CSV")

    def test_empty_or_only_choice_has_no_recommendation(self):
        self.assertEqual(mark_recommended([]), [])
        self.assertEqual(mark_recommended(["CSV"]), ["CSV"])
        self.assertEqual(mark_recommended(["", "JSON"]), ["", "JSON"])

    def test_only_suffix_is_removed_and_unicode_answer_is_preserved(self):
        self.assertEqual(strip_recommended("  BTC/ETH · отчёт (Recommended)  "), "BTC/ETH · отчёт")
        self.assertEqual(strip_recommended("(Recommended) — это название"), "(Recommended) — это название")
        self.assertEqual(strip_recommended("  Цена (USD)  "), "Цена (USD)")

    def test_display_to_answer_round_trip_keeps_bare_meaning(self):
        choices = ["Посчитать реализованный PnL", "Показать позиции"]
        self.assertEqual([strip_recommended(value) for value in mark_recommended(choices)], choices)


if __name__ == "__main__":
    unittest.main()
