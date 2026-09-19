import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import worker_eval


class WorkerEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "demo-project").mkdir()
        self.source = (worker_eval.ROOT / "demo-project" / "app.py").read_text()
        (self.root / "demo-project" / "app.py").write_text(self.source)
        self.config = self.root / "worker-config-codex.json"
        self.config.write_text(json.dumps({"argv": ["python3", str(self.root / "adapters" / "codex_cli.py")]}))
        self.policy = self.root / "policy-codex.json"
        self.policy.write_text(json.dumps({"max_iterations": 2, "max_seconds": 300}))
        self.out = self.root / "runs" / "worker-eval-test"

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

    def test_preregistered_inputs_and_oracle_order_with_fake_worker(self):
        order = []

        def fake_process(argv, **kwargs):
            manifest = json.loads((self.out / "manifest.json").read_text())
            self.assertEqual(len(manifest["cases"]), 3)
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

    def test_timeout_recorded_without_false_completion(self):
        with patch.object(worker_eval, "ROOT", self.root), \
                patch.object(worker_eval, "run_process", side_effect=subprocess.TimeoutExpired("run.py", 330)), \
                patch.object(worker_eval, "independent_acceptance", return_value={"passed": False, "observations": []}):
            rows = worker_eval.evaluate(self.out, self.config, self.policy)
        self.assertEqual([row["status"] for row in rows], ["error"] * 3)
        self.assertFalse(any(row["false_complete"] for row in rows))


if __name__ == "__main__":
    unittest.main()
