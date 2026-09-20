"""Regressions for real HTTP accounting and optional model annotations."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from judge import Judge, JudgeError, TICKET_QUESTIONS, demo_response, validate_response
from evidence import load_state, snapshot
import run


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return json.dumps(self.value).encode()[:size]


class LiveBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_model_and_usage_cannot_be_accepted_as_valid_response(self):
        for field in ("model", "usage", "input_tokens", "output_tokens"):
            value = demo_response(TICKET_QUESTIONS)
            target = value["usage"] if field.endswith("tokens") else value
            target.pop(field)
            with self.subTest(field=field), self.assertRaises(JudgeError):
                validate_response(value, TICKET_QUESTIONS)

    def test_unhashable_choice_is_a_controlled_protocol_error(self):
        for choice in ([], {}):
            value = demo_response(TICKET_QUESTIONS)
            value["answers"]["category"]["choice"] = choice
            with self.subTest(choice=choice), self.assertRaises(JudgeError):
                validate_response(value, TICKET_QUESTIONS)

    def test_invalid_answer_preserves_reported_tokens_and_marks_run_incomplete(self):
        value = demo_response(TICKET_QUESTIONS)
        value["usage"] = {"input_tokens": 123, "output_tokens": 45}
        value["answers"]["category"]["choice"] = []
        judge = Judge("live", self.directory / "judge")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fixture-not-a-real-key"}), \
                patch("urllib.request.urlopen", return_value=Response(value)):
            with self.assertRaises(JudgeError):
                judge.ask("test", TICKET_QUESTIONS)
        self.assertEqual(judge.usage, {"input_tokens": 123, "output_tokens": 45})
        self.assertEqual(judge.usage_reported_requests, 1)
        self.assertFalse(judge.usage_complete)
        record = json.loads((self.directory / "judge/judge-001.json").read_text())
        self.assertTrue(record["usage_reported"])
        self.assertFalse(record["usage_complete"])
        self.assertEqual(record["response"], value)

    def test_missing_usage_is_unknown_instead_of_a_free_success(self):
        value = demo_response(TICKET_QUESTIONS)
        value.pop("usage")
        judge = Judge("live", self.directory / "judge")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fixture"}), \
                patch("urllib.request.urlopen", return_value=Response(value)):
            with self.assertRaisesRegex(JudgeError, "usage"):
                judge.ask("test", TICKET_QUESTIONS)
        self.assertFalse(judge.usage_complete)
        self.assertEqual((judge.remote_requests, judge.usage_reported_requests), (1, 0))

    def test_http_error_logs_only_safe_request_id_and_unknown_usage(self):
        secret = "fixture-secret-not-a-real-key"
        headers = {"x-request-id": "req-123-abc", "Authorization": "Bearer " + secret,
                   "Set-Cookie": "sensitive-cookie"}
        error = urllib.error.HTTPError("https://api.typesafe.ai/v1/systemone", 429,
                                       "rate limited", headers, None)
        judge = Judge("live", self.directory / "judge")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": secret}), \
                patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(JudgeError, "HTTP 429"):
                judge.ask("test", TICKET_QUESTIONS)
        logged = (self.directory / "judge/judge-001.json").read_text()
        self.assertNotIn(secret, logged)
        self.assertNotIn("sensitive-cookie", logged)
        self.assertEqual(json.loads(logged)["provider_request_id"], "req-123-abc")
        self.assertFalse(judge.usage_complete)
        self.assertEqual(judge.usage_reported_requests, 0)

    def test_success_after_failure_does_not_erase_incomplete_usage(self):
        value = demo_response(TICKET_QUESTIONS)
        value["usage"] = {"input_tokens": 100, "output_tokens": 20}
        judge = Judge("live", self.directory / "judge")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fixture"}), \
                patch("urllib.request.urlopen", side_effect=[TimeoutError(), Response(value)]):
            with self.assertRaises(JudgeError):
                judge.ask("test", TICKET_QUESTIONS)
            judge.ask("test", TICKET_QUESTIONS)
        self.assertEqual(judge.usage, value["usage"])
        self.assertEqual((judge.remote_requests, judge.usage_reported_requests), (2, 1))
        self.assertFalse(judge.usage_complete)

    def run_lab(self, case, ask):
        out = self.directory / "run"
        argv = ["run.py", "loop", "--case", case, "--mode", "live", "--out", str(out)]
        with patch("sys.argv", argv), patch.object(Judge, "ask", side_effect=ask), \
                contextlib.redirect_stdout(io.StringIO()):
            code = run.main()
        return code, json.loads((out / "result.json").read_text()), out

    def test_scope_http_failure_cannot_stop_verified_correct_project(self):
        code, result, out = self.run_lab("correct", JudgeError("HTTP 503"))
        self.assertEqual((code, result["status"], result["checks_executed"]), (0, "complete", 2))
        report = json.loads((out / "evidence-report.json").read_text())
        self.assertTrue(report["all_passed"])
        self.assertEqual(report["scope_annotation_error"], "HTTP 503")
        self.assertTrue(all(row["scope_noul"] is None for row in report["criteria"]))
        self.assertIn("Shadow scope annotation unavailable", (out / "run-report.md").read_text())

    def test_choice_router_failure_still_stops_before_worker(self):
        def ask(state, questions):
            if "next_diagnostic" in questions:
                raise JudgeError("HTTP 503")
            return demo_response(questions)
        code, result, out = self.run_lab("missing-evidence", ask)
        self.assertEqual((code, result["status"], result["reason"]), (2, "stop", "HTTP 503"))
        self.assertEqual(result["worker_iterations"], 0)
        self.assertFalse(json.loads((out / "evidence-report.json").read_text())["all_passed"])

    def test_scope_global_limit_is_not_swallowed(self):
        code, result, _ = self.run_lab("correct", run.LimitError("time_limit"))
        self.assertEqual((code, result["status"], result["reason"]), (2, "stop", "time_limit"))

    def test_sibling_project_state_survives_moving_whole_evaluation(self):
        original = self.directory / "original-matrix"
        project = original / "seed" / "project"
        shutil.copytree(ROOT / "demo-project", project)
        lab = object.__new__(run.Lab)
        lab.directory = original / "run"
        lab.directory.mkdir()
        lab.state = {"project": str(project), "snapshot": snapshot(project), "records": []}
        lab.save_state()
        self.assertEqual(lab.state["project_relative_to_state"], "../seed/project")
        copied = self.directory / "copied-matrix"
        shutil.copytree(original, copied)
        shutil.rmtree(original)
        loaded = load_state(copied / "run" / "state.json")
        self.assertEqual(Path(loaded["project"]), (copied / "seed" / "project").resolve())
        self.assertEqual(loaded["snapshot"], lab.state["snapshot"])


if __name__ == "__main__":
    unittest.main()
