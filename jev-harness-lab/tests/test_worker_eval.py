import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import worker_eval


class WorkerEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in worker_eval.SOURCE_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((worker_eval.ROOT / name).read_bytes())
        (self.root / "demo-project").mkdir()
        self.source = (worker_eval.ROOT / "demo-project" / "app.py").read_text()
        (self.root / "demo-project" / "app.py").write_text(self.source)
        self.config = self.root / "worker-config-codex.json"
        self.config.write_text(json.dumps({"argv": ["python3", str(self.root / "adapters" / "codex_cli.py")]}))
        self.policy = self.root / "policy-codex.json"
        self.policy.write_text(json.dumps({"max_iterations": 2, "max_seconds": 300}))
        self.out = self.root / "runs" / "worker-eval-test"

    def fake_process(self, selector, *, judge_calls=0, remote_requests=0, usage=None, usage_complete=None):
        def process(argv, **kwargs):
            self.assertEqual(argv[argv.index("--selector") + 1], selector)
            manifest = json.loads((self.out / "manifest.json").read_text())
            self.assertEqual(manifest["selector"], selector)
            self.assertEqual(len(manifest["cases"]), 3)
            self.assertEqual(manifest["policy_sha256"], hashlib.sha256(self.policy.read_bytes()).hexdigest())
            self.assertEqual(set(manifest["source_sha256"]), set(worker_eval.SOURCE_FILES))
            for name, digest in manifest["source_sha256"].items():
                self.assertEqual(digest, hashlib.sha256((self.root / name).read_bytes()).hexdigest())
            out = Path(argv[argv.index("--out") + 1])
            out.mkdir()
            (out / "result.json").write_text(json.dumps({
                "status": "complete", "reason": "acceptance_contract_satisfied",
                "checks_executed": 5, "worker_iterations": 1, "remote_jev_requests": remote_requests,
                "judge_invocations": judge_calls, "usage": usage, "usage_complete": usage_complete,
                "judge_elapsed_ms": 31.5, "elapsed_ms": 100}))
            decisions = [
                {"action": "check", "check_id": "C2", "reason": "mandatory_acceptance"},
                {"action": "ask_router", "reason": "choose_optional_diagnostic"},
                {"action": "check", "check_id": "D2", "reason": "jev_selected_diagnostic"},
                {"action": "worker", "reason": "repair"},
                {"action": "complete", "reason": "acceptance_contract_satisfied"},
            ]
            (out / "events.jsonl").write_text("\n".join(json.dumps({"index": i, "decision": d})
                                                         for i, d in enumerate(decisions)))
            return subprocess.CompletedProcess(argv, 0, "", "")
        return process

    def test_three_faults_are_distinct_and_break_description_search(self):
        sources = worker_eval.fault_variants(self.source)
        self.assertEqual(tuple(sources), worker_eval.CASE_NAMES)
        self.assertEqual(len(set(sources.values())), 3)
        for name, source in sources.items():
            namespace = {}
            exec(compile(source, name, "exec"), namespace)
            self.assertEqual(namespace["search"]("blue"), [])
            self.assertEqual([item["id"] for item in namespace["search"]("MILK")], [1])
            direct = namespace["api_search"]("blue", ["title", "description"])
            self.assertEqual(bool(direct), name == "ui-title-only")

    def test_outside_runs_rejected_before_writes_or_calls(self):
        with patch.object(worker_eval, "ROOT", self.root), self.assertRaisesRegex(ValueError, "under.*runs"):
            worker_eval.prepare(self.root / "wrong-place", self.config, self.policy)
        self.assertFalse((self.root / "wrong-place").exists())

    def test_unknown_selector_rejected_before_writes(self):
        with patch.object(worker_eval, "ROOT", self.root), self.assertRaisesRegex(ValueError, "selector"):
            worker_eval.prepare(self.out, self.config, self.policy, "invented")
        self.assertFalse(self.out.exists())

    def test_preregistered_inputs_and_oracle_order_with_fake_worker(self):
        order = []

        def fake_process(argv, **kwargs):
            manifest = json.loads((self.out / "manifest.json").read_text())
            self.assertEqual(len(manifest["cases"]), 3)
            self.assertEqual(manifest["selector"], "fixed")
            self.assertEqual(manifest["remote_jev_requests_expected"], 0)
            self.assertIn("run.py", manifest["source_sha256"])
            self.assertIn("judge.py", manifest["source_sha256"])
            for case in manifest["cases"]:
                self.assertTrue((self.out / case["initial_source_file"]).is_file())
            self.assertEqual(kwargs["timeout"], 330)
            self.assertEqual(argv[argv.index("--selector") + 1], "fixed")
            self.assertEqual(argv[argv.index("--mode") + 1], "live")
            state = json.loads(Path(argv[argv.index("--state") + 1]).read_text())
            self.assertEqual(state["records"], [])
            self.assertNotIn("oracle", json.dumps(state))
            out = Path(argv[argv.index("--out") + 1])
            out.mkdir()
            order.append("worker")
            (out / "result.json").write_text(json.dumps({"status": "complete", "reason": "acceptance_contract_satisfied",
                "checks_executed": 5, "worker_iterations": 1, "remote_jev_requests": 0,
                "judge_invocations": 0, "elapsed_ms": 100}))
            (out / "worker-001.json").write_text(json.dumps({"synthetic": False, "stderr": json.dumps({
                "provider": "codex_cli", "usage": {"input_tokens": 10, "output_tokens": 5}})}))
            return subprocess.CompletedProcess(argv, 0, "", "")

        def fake_oracle(project):
            self.assertEqual(order[-1], "worker")
            order.append("oracle")
            return {"passed": True, "observations": []}

        with patch.object(worker_eval, "ROOT", self.root), \
                patch.object(worker_eval, "run_process", side_effect=fake_process), \
                patch.object(worker_eval, "independent_acceptance", side_effect=fake_oracle):
            rows = worker_eval.evaluate(self.out, self.config, self.policy)
        self.assertEqual(order, ["worker", "oracle"] * 3)
        self.assertEqual([row["iterations"] for row in rows], [1, 1, 1])
        self.assertEqual(rows[0]["worker_calls"][0]["usage"]["input_tokens"], 10)
        self.assertFalse(any(row["false_complete"] for row in rows))
        saved = json.loads((self.out / "evaluation.json").read_text())
        self.assertEqual(saved["completed_cases"], 3)
        self.assertTrue((self.out / "evaluation.md").is_file())

    def test_jev_records_real_request_counters_usage_and_selected_diagnostics(self):
        usage = {"input_tokens": 420, "output_tokens": 15}
        with patch.object(worker_eval, "ROOT", self.root), \
                patch.object(worker_eval, "run_process", side_effect=self.fake_process(
                    "jev", judge_calls=3, remote_requests=3, usage=usage, usage_complete=False)), \
                patch.object(worker_eval, "independent_acceptance", return_value={"passed": True, "observations": []}):
            rows = worker_eval.evaluate(self.out, self.config, self.policy, selector="jev")
        for row in rows:
            self.assertEqual(row["selector"], "jev")
            self.assertEqual(row["judge_invocations"], 3)
            self.assertEqual(row["remote_jev_requests"], 3)
            self.assertEqual(row["jev_usage"], usage)
            self.assertIs(row["jev_usage_complete"], False)
            self.assertEqual(row["judge_elapsed_ms"], 31.5)
            self.assertEqual(row["harness_elapsed_ms"], 100)
            self.assertGreaterEqual(row["elapsed_ms"], 0)
            self.assertEqual(row["diagnostic_actions"], [{"event_index": 2, "action": "check",
                "check_id": "D2", "reason": "jev_selected_diagnostic"}])
            self.assertIsNone(row["diagnostic_actions_error"])
            self.assertEqual(len(row["initial_sha256"]), 64)
            self.assertEqual(len(row["final_sha256"]), 64)
        manifest = json.loads((self.out / "manifest.json").read_text())
        self.assertIsNone(manifest["remote_jev_requests_expected"])
        self.assertTrue(manifest["jev_requests_enabled"])
        saved = json.loads((self.out / "evaluation.json").read_text())
        self.assertEqual(saved["selector"], "jev")
        report = (self.out / "evaluation.md").read_text()
        self.assertIn("Live Jev", report)
        self.assertNotIn("No Jev calls", report)

    def test_all_baseline_routes_without_judge(self):
        with patch.object(worker_eval, "ROOT", self.root), \
                patch.object(worker_eval, "run_process", side_effect=self.fake_process("all")), \
                patch.object(worker_eval, "independent_acceptance", return_value={"passed": True, "observations": []}):
            rows = worker_eval.evaluate(self.out, self.config, self.policy, selector="all")
        self.assertEqual([row["status"] for row in rows], ["complete"] * 3)
        self.assertEqual([row["judge_invocations"] for row in rows], [0] * 3)
        self.assertTrue(all(row["jev_usage_complete"] is None for row in rows))
        self.assertIn("both available diagnostics", (self.out / "evaluation.md").read_text())

    def test_baselines_reject_unexpected_judge_calls(self):
        for selector in ("fixed", "all"):
            with self.subTest(selector=selector):
                self.out = self.root / "runs" / ("unexpected-" + selector)
                with patch.object(worker_eval, "ROOT", self.root), \
                        patch.object(worker_eval, "run_process", side_effect=self.fake_process(selector, judge_calls=1)), \
                        patch.object(worker_eval, "independent_acceptance", return_value={"passed": True, "observations": []}):
                    rows = worker_eval.evaluate(self.out, self.config, self.policy, selector)
                self.assertEqual([row["status"] for row in rows], ["error"] * 3)
                self.assertTrue(all(row["reason"] == "unexpected_judge_call_in_%s_baseline" % selector for row in rows))
                self.assertTrue(all(row["judge_invocations"] == 1 for row in rows))

    def test_broken_event_log_preserves_recorded_actions_and_marks_incomplete(self):
        self.out.mkdir(parents=True)
        event = {"index": 4, "decision": {"action": "check", "check_id": "D1", "reason": "fixed"}}
        (self.out / "events.jsonl").write_text(json.dumps(event) + "\n{broken")
        actions, error = worker_eval.diagnostic_actions(self.out)
        self.assertEqual(actions, [{"event_index": 4, **event["decision"]}])
        self.assertEqual(error, "incomplete_or_invalid_events")

    def test_cli_passes_selected_policy(self):
        with patch.object(sys, "argv", ["worker_eval.py", "--out", str(self.out), "--selector", "jev"]), \
                patch.object(worker_eval, "evaluate", return_value=[{"status": "complete",
                            "independent_acceptance": {"passed": True}}]) as evaluate:
            self.assertEqual(worker_eval.main(), 0)
        self.assertEqual(evaluate.call_args.args[-1], "jev")

    def test_timeout_recorded_without_false_completion(self):
        with patch.object(worker_eval, "ROOT", self.root), \
                patch.object(worker_eval, "run_process", side_effect=subprocess.TimeoutExpired("run.py", 330)), \
                patch.object(worker_eval, "independent_acceptance", return_value={"passed": False, "observations": []}):
            rows = worker_eval.evaluate(self.out, self.config, self.policy)
        self.assertEqual([row["status"] for row in rows], ["error"] * 3)
        self.assertFalse(any(row["false_complete"] for row in rows))


if __name__ == "__main__":
    unittest.main()
