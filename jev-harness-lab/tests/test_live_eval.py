import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import live_eval
from judge import JudgeError


class LiveEvalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name) / "evaluation"
        self.cases = live_eval.load_cases()["cases"]

    def tearDown(self):
        self.temp.cleanup()

    def answer(self, question, selected, confidence=0.9):
        if question["type"] == "noul":
            return {"type": "noul", "noul": 0.9 if selected else 0.1}
        alternatives = len(question["criteria"]) - 1
        return {"type": "choice", "choice": selected, "confidence": confidence,
                "probabilities": {key: 0.9 if key == selected else 0.1 / alternatives for key in question["criteria"]}}

    def test_dataset_is_bilingual_and_bounded_and_has_none_suitable(self):
        self.assertEqual(len(self.cases), 18)
        self.assertEqual({case["language"] for case in self.cases}, {"en", "ru"})
        self.assertEqual(sum(len(case["expected"]) for case in self.cases), 28)
        diagnostic_labels = [case["expected"]["next_check"] for case in self.cases if case["kind"] == "diagnostic"]
        self.assertEqual(diagnostic_labels.count("none_suitable"), 2)

    def test_dry_run_never_calls_judge_or_fabricates_predictions(self):
        def forbidden(*args, **kwargs):
            self.fail("Dry run attempted to construct a judge")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-secret"}):
            result = live_eval.evaluate(self.out, dry_run=True, judge_factory=forbidden)
        self.assertEqual((result["remote_requests"], result["answers"]), (0, []))
        self.assertEqual(result["metrics"]["unanswered"], 28)
        self.assertIsNone(result["metrics"]["raw_accuracy_on_valid"])
        self.assertEqual(len(list((self.out / "requests").glob("*.json"))), 18)
        self.assertFalse((self.out / "judge").exists())
        self.assertIn("No Jev predictions", (self.out / "report.md").read_text())
        self.assertNotIn("test-secret", "".join(p.read_text() for p in self.out.rglob("*.json")))

    def test_missing_credentials_saved_without_network_attempt(self):
        with patch.dict(os.environ, {}, clear=True):
            result = live_eval.evaluate(self.out)
        self.assertEqual((result["mode"], result["status"]), ("no-credentials", "credentials_required"))
        self.assertEqual(result["remote_requests"], 0)
        self.assertEqual(result["answers"], [])

    def test_request_does_not_contain_gold_or_case_metadata(self):
        for case in self.cases:
            request = live_eval.make_request(case, "test-model")
            self.assertEqual(set(request), {"state", "model", "questions"})
            self.assertNotIn("expected", request)
            self.assertNotIn("case_id", request)
            self.assertNotIn("expected", request["state"])
            altered = copy.deepcopy(case)
            altered["expected"] = {"deliberately": "wrong"}
            self.assertEqual(request, live_eval.make_request(altered, "test-model"))

    def test_uncertainty_abstention_is_not_none_suitable(self):
        case = next(c for c in self.cases if c["expected"].get("next_check") == "none_suitable")
        question = live_eval.questions_for(case)["next_check"]
        low = live_eval.score_answer(case, "next_check", self.answer(question, "none_suitable", 0.2))
        self.assertTrue(low["raw_correct"])
        self.assertTrue(low["policy_abstained"])
        self.assertFalse(low["explicit_none_suitable"])
        high = live_eval.score_answer(case, "next_check", self.answer(question, "none_suitable", 0.9))
        self.assertTrue(high["policy_correct"])
        self.assertTrue(high["explicit_none_suitable"])
        metrics = live_eval.summarize([low, high], 3)
        self.assertEqual(metrics["valid_answers"], 2)
        self.assertEqual(metrics["unanswered"], 1)
        self.assertEqual(metrics["accepted_decisions"], 1)
        self.assertEqual(metrics["decision_coverage"], 0.333333)
        self.assertEqual(metrics["accuracy_on_accepted"], 1)

    def test_noul_threshold_boundaries_and_wrong_accepted_prediction(self):
        case = self.cases[0]  # Gold workaround is true.
        for value, abstained, correct in ((0.2, False, False), (0.200001, True, None),
                                           (0.799999, True, None), (0.8, False, True)):
            row = live_eval.score_answer(case, "has_workaround", {"type": "noul", "noul": value})
            self.assertEqual((row["policy_abstained"], row["policy_correct"]), (abstained, correct))
        wrong = live_eval.score_answer(case, "has_workaround", {"type": "noul", "noul": 0.1})
        self.assertEqual(live_eval.summarize([wrong], 1)["accepted_incorrect"], 1)

    def test_mocked_live_roundtrip_records_responses_and_metrics(self):
        test = self
        seen = []
        class MockJudge:
            def __init__(self, *args, **kwargs):
                self.remote_requests = 0
                self.usage = {"input_tokens": 0, "output_tokens": 0}
                self.total_ms = 0
            def ask(self, state, questions):
                self.remote_requests += 1
                self.usage["input_tokens"] += 11
                self.usage["output_tokens"] += 3
                self.total_ms += 2
                case = next(c for c in test.cases if c["state"] == state)
                seen.append((state, questions))
                return {"model": "MOCK-ONLY", "id": "fake-%s" % self.remote_requests,
                        "system_fingerprint": "test-fingerprint", "extra_provider_field": "preserve-me",
                        "answers": {key: test.answer(questions[key], case["expected"][key]) for key in questions},
                        "usage": {"input_tokens": 11, "output_tokens": 3}}
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "mock-key"}):
            result = live_eval.evaluate(self.out, judge_factory=MockJudge)
        self.assertEqual(len(seen), 18)
        self.assertEqual((result["remote_requests"], result["valid_responses"]), (18, 18))
        self.assertEqual(result["metrics"]["raw_correct"], 28)
        self.assertEqual(result["metrics"]["explicit_none_suitable"], 2)
        self.assertEqual(result["usage"], {"input_tokens": 198, "output_tokens": 54})
        preserved = json.loads((self.out / (self.cases[0]["id"] + "-response.json")).read_text())
        self.assertEqual(preserved["extra_provider_field"], "preserve-me")
        self.assertEqual(result["requests"][0]["provider_metadata"]["system_fingerprint"], "test-fingerprint")

    def test_first_api_failure_stops_without_retry_or_inflating_success(self):
        class BrokenJudge:
            def __init__(self, *args, **kwargs):
                self.remote_requests = 0
                self.usage = {"input_tokens": 0, "output_tokens": 0}
                self.total_ms = 7
            def ask(self, state, questions):
                self.remote_requests += 1
                raise JudgeError("HTTP 401")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "mock-key"}):
            result = live_eval.evaluate(self.out, judge_factory=BrokenJudge)
        self.assertEqual((result["remote_requests"], result["request_errors"]), (1, 1))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["metrics"]["unanswered"], 28)
        self.assertEqual(sum(r["status"] == "skipped_after_error" for r in result["requests"]), 17)
        self.assertIsNone(result["metrics"]["accuracy_on_accepted"])

    def test_existing_output_directory_not_overwritten(self):
        self.out.mkdir()
        marker = self.out / "preserve.txt"
        marker.write_text("original")
        with self.assertRaises(FileExistsError):
            live_eval.evaluate(self.out, dry_run=True)
        self.assertEqual(marker.read_text(), "original")

    def test_invalid_timeout_fails_before_any_output(self):
        for timeout in (0, -1, 30.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                live_eval.evaluate(self.out, dry_run=True, timeout=timeout)
        self.assertFalse(self.out.exists())

    def test_dataset_over_budget_and_invalid_gold_rejected(self):
        document = live_eval.load_cases()
        path = Path(self.temp.name) / "bad.json"
        document["cases"].append(copy.deepcopy(document["cases"][0]))
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, "1..18"):
            live_eval.load_cases(path)
        document["cases"].pop()
        document["cases"][0]["expected"]["category"] = "invented-label"
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, "outside criteria"):
            live_eval.load_cases(path)


if __name__ == "__main__":
    unittest.main()
