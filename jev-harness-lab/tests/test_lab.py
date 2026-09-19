import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evidence import build_report, contract_hash, current_record, load_state, run_check, snapshot
from judge import Judge, JudgeError, TICKET_QUESTIONS, demo_response, validate_response
from policy import decide, load_policy
from worker import WorkerError, run_worker
from run import Lab
from evaluate import independent_acceptance


class LabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.project = self.directory / "project"
        shutil.copytree(ROOT / "demo-project", self.project)
        self.state = {"project": str(self.project), "snapshot": snapshot(self.project),
                      "case": "missing-evidence", "records": []}
        self.policy = load_policy()

    def tearDown(self):
        self.temp.cleanup()

    def context(self, report):
        return {"report": report, "checks_used": 2, "jev_calls": 1, "iterations": 0,
                "elapsed_seconds": 0, "diagnostics_done": False,
                "router_asked": True, "router_answer": {"choice": "none_suitable", "confidence": 1}}

    def failed_report(self):
        self.state["records"] = [run_check("C1", self.project, 2), run_check("C2", self.project, 2)]
        return build_report(self.state, {}, 0.8)

    def test_actual_description_failure(self):
        report = self.failed_report()
        self.assertEqual([r["status"] for r in report["criteria"]], ["passed", "failed"])
        self.assertIn("description-only", report["criteria"][1]["record"]["stdout"])

    def test_missing_is_unverified_even_if_judge_says_yes(self):
        report = build_report(self.state, {"scope_R2": {"noul": 1}}, 0.8)
        self.assertEqual(report["criteria"][1]["status"], "unverified")

    def test_shadow_noul_cannot_downgrade_known_pass(self):
        self.state["records"] = [run_check("C1", self.project, 2)]
        report = build_report(self.state, {"scope_R1": {"noul": 0}}, 0.8)
        self.assertEqual(report["criteria"][0]["status"], "passed")
        self.assertFalse(report["criteria"][0]["scope_supported"])

    def test_source_mutation_makes_old_evidence_stale(self):
        self.state["records"] = [run_check("C1", self.project, 2)]
        with (self.project / "app.py").open("a") as f:
            f.write("\n# changed\n")
        self.state["snapshot"] = snapshot(self.project)
        self.assertIsNone(current_record(self.state, "C1"))

    def test_changed_contract_makes_old_evidence_stale(self):
        self.state["records"] = [run_check("C1", self.project, 2)]
        self.state["records"][0]["contract_sha256"] = "retired"
        self.assertIsNone(current_record(self.state, "C1"))

    def test_tool_error_is_not_assertion_failure(self):
        (self.project / "app.py").write_text("this is invalid python !!!")
        self.state["snapshot"] = snapshot(self.project)
        self.state["records"] = [run_check("C1", self.project, 2)]
        row = build_report(self.state, {}, 0.8)["criteria"][0]
        self.assertEqual((row["status"], row["reason"]), ("unverified", "check_tool_error"))

    def test_early_successful_exit_is_not_acceptance(self):
        for source in ("import sys; sys.exit(0)", "import os; os._exit(0)"):
            with self.subTest(source=source):
                (self.project / "app.py").write_text(source)
                self.state["snapshot"] = snapshot(self.project)
                self.state["records"] = [run_check("C1", self.project, 2)]
                row = build_report(self.state, {}, 0.8)["criteria"][0]
                self.assertEqual((row["status"], row["reason"]), ("unverified", "check_tool_error"))

    def test_application_logging_does_not_hide_completed_check(self):
        path = self.project / "app.py"
        path.write_text("print('application log line')\n" + path.read_text())
        record = run_check("C1", self.project, 2)
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["check_result"]["observation"]["actual_ids"], [1])

    def test_check_that_edits_source_cannot_supply_fresh_evidence(self):
        path = self.project / "app.py"
        path.write_text(path.read_text() + "\nfrom pathlib import Path\nPath(__file__).write_text(Path(__file__).read_text() + '\\n# mutated during check')\n")
        self.state["records"] = [run_check("C1", self.project, 2)]
        self.state["snapshot"] = snapshot(self.project)
        self.assertEqual(self.state["records"][0]["exit_code"], 0)
        self.assertIsNone(current_record(self.state, "C1"))

    def test_contract_changed_during_execution_is_not_fresh(self):
        actual = contract_hash()
        with patch("evidence.contract_hash", side_effect=["contract-before-change", actual]):
            record = run_check("C1", self.project, 2)
        self.state["records"] = [record]
        self.assertIsNone(current_record(self.state, "C1"))

    def test_latest_failure_overrides_earlier_success(self):
        passed = run_check("C1", self.project, 2)
        failed = dict(passed, exit_code=1)
        self.state["records"] = [passed, failed]
        self.assertEqual(build_report(self.state, {}, .8)["criteria"][0]["status"], "failed")

    def test_stale_diagnostic_is_not_sent_to_worker(self):
        stale = run_check("D1", self.project, 2)
        stale["contract_sha256"] = "retired"
        self.state["records"] = [stale]
        lab = object.__new__(Lab)
        lab.state = self.state
        self.assertEqual(lab.current_diagnostics(), [])

    def test_diagnostic_retry_replaces_previous_error(self):
        success = run_check("D1", self.project, 2)
        self.state["records"] = [dict(success, exit_code=2), success]
        lab = object.__new__(Lab)
        lab.state = self.state
        self.assertEqual(lab.current_diagnostics(), [success])

    def test_malformed_imports_are_rejected_cleanly(self):
        valid = dict(self.state, records=[run_check("C1", self.project, 2)])
        changes = [lambda s: s.update(project=None),
                   lambda s: s.update(project_relative_to_state=[]),
                   lambda s: s.update(records=[None]),
                   lambda s: s["records"][0].update(check_id=[]),
                   lambda s: s["records"][0].update(exit_code=False),
                   lambda s: s["records"][0].update(exit_code="0"),
                   lambda s: s["records"][0].update(snapshot=[]) ]
        for mutate in changes:
            with self.subTest(mutate=mutate):
                value = copy.deepcopy(valid)
                mutate(value)
                path = self.directory / "bad-state.json"
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    load_state(path)

    def test_partial_or_duplicate_acceptance_report_cannot_complete(self):
        report = self.failed_report()
        for row in report["criteria"]:
            row["status"] = "passed"
        variants = [report["criteria"][:1], [report["criteria"][0]] * 2,
                    [], [None, None]]
        for rows in variants:
            with self.subTest(rows=rows):
                context = self.context(dict(report, criteria=rows))
                self.assertEqual(decide(context, self.policy)["reason"], "invalid_acceptance_report")

    def test_none_suitable_stops(self):
        action = decide(self.context(self.failed_report()), self.policy)
        self.assertEqual(action["reason"], "no_supported_diagnostic")

    def test_diagnostic_tool_error_stops(self):
        context = self.context(self.failed_report())
        context.update(diagnostics_done=True, diagnostic_errors=True)
        self.assertEqual(decide(context, self.policy)["reason"], "diagnostic_tool_error")

    def test_low_confidence_stops(self):
        context = self.context(self.failed_report())
        context["router_answer"] = {"choice": "D2", "confidence": 0.2}
        self.assertEqual(decide(context, self.policy)["action"], "stop")

    def test_unknown_model_command_stops(self):
        context = self.context(self.failed_report())
        context["router_answer"] = {"choice": "rm -rf something", "confidence": 1}
        self.assertEqual(decide(context, self.policy)["action"], "stop")

    def test_check_limit_cannot_be_overridden(self):
        context = self.context(build_report(self.state, {}, 0.8))
        context["checks_used"] = self.policy["max_checks"]
        self.assertEqual(decide(context, self.policy)["reason"], "check_limit")

    def test_iteration_limit(self):
        context = self.context(self.failed_report())
        context.update(diagnostics_done=True, iterations=self.policy["max_iterations"])
        self.assertEqual(decide(context, self.policy)["reason"], "iteration_limit")

    def test_time_limit(self):
        context = self.context(self.failed_report())
        context["elapsed_seconds"] = self.policy["max_seconds"]
        self.assertEqual(decide(context, self.policy)["reason"], "time_limit")

    def test_jev_call_limit(self):
        context = self.context(self.failed_report())
        context.update(router_asked=False, jev_calls=self.policy["max_jev_calls"])
        self.assertEqual(decide(context, self.policy)["reason"], "jev_call_limit")

    def test_invalid_probability_and_score_rejected(self):
        for mutate in (lambda r: r["answers"]["has_workaround"].update(noul=float("nan")),
                       lambda r: r["answers"]["impact"].pop("legend"),
                       lambda r: r["answers"]["impact"].update(score=1.8),
                       lambda r: r["answers"]["category"].update(choice="account")):
            response = demo_response(TICKET_QUESTIONS)
            mutate(response)
            with self.assertRaises(JudgeError):
                validate_response(response, TICKET_QUESTIONS)

    def test_malformed_usage_is_reported_as_judge_error(self):
        for usage in ([], None, {"input_tokens": True}, {"output_tokens": -1}):
            response = demo_response(TICKET_QUESTIONS)
            response["usage"] = usage
            with self.subTest(usage=usage), self.assertRaises(JudgeError):
                validate_response(response, TICKET_QUESTIONS)

    def test_api_error_preserved_without_credentials(self):
        judge = Judge("live", self.directory / "judge")
        fake = "fixture-secret-not-a-real-key"
        error = urllib.error.HTTPError("https://api.typesafe.ai/v1/systemone", 429, "rate limited", {}, None)
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": fake}), patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(JudgeError, "HTTP 429"):
                judge.ask("data", TICKET_QUESTIONS)
        logged = (self.directory / "judge" / "judge-001.json").read_text()
        self.assertNotIn(fake, logged)
        self.assertIn("HTTP 429", logged)

    def test_missing_key_does_not_count_as_remote_request(self):
        judge = Judge("live", self.directory / "judge")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(JudgeError):
                judge.ask("data", TICKET_QUESTIONS)
        self.assertEqual(judge.remote_requests, 0)

    def test_api_total_deadline(self):
        judge = Judge("live", self.directory / "judge", timeout=0.05)
        def slow(*args, **kwargs):
            time.sleep(1)
        started = time.monotonic()
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "fixture"}), patch("urllib.request.urlopen", side_effect=slow):
            with self.assertRaisesRegex(JudgeError, "TimeoutError"):
                judge.ask("data", TICKET_QUESTIONS)
        self.assertLess(time.monotonic() - started, 0.5)

    def test_worker_timeout_kills_descendant(self):
        marker = self.directory / "late-write"
        child = "import time; from pathlib import Path; time.sleep(.5); Path(%r).write_text('bad')" % str(marker)
        adapter = self.directory / "adapter.py"
        adapter.write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c',%r])\ntime.sleep(5)\n" % child)
        config = self.directory / "worker.json"
        config.write_text(json.dumps({"argv": [sys.executable, str(adapter)]}))
        with self.assertRaisesRegex(WorkerError, "worker_timeout"):
            run_worker("live", self.state, "task", {}, 1, config, 0.1)
        time.sleep(0.6)
        self.assertFalse(marker.exists())

    def test_successful_worker_cannot_leave_background_writer(self):
        marker = self.directory / "late-successful-write"
        child = "import time; from pathlib import Path; time.sleep(.4); Path(%r).write_text('bad')" % str(marker)
        adapter = self.directory / "success-adapter.py"
        adapter.write_text("import subprocess,sys,json\nsubprocess.Popen([sys.executable,'-c',%r], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\nprint(json.dumps({'claim':'done'}))\n" % child)
        config = self.directory / "success-worker.json"
        config.write_text(json.dumps({"argv": [sys.executable, str(adapter)]}))
        result = run_worker("live", self.state, "task", {}, 1, config, 2)
        self.assertEqual(result["claim"], "done")
        time.sleep(.5)
        self.assertFalse(marker.exists())

    def test_worker_config_requires_object(self):
        config = self.directory / "bad-worker.json"
        config.write_text("[]")
        with self.assertRaisesRegex(WorkerError, "JSON object"):
            run_worker("live", self.state, "task", {}, 1, config, 2)

    def test_independent_oracle_preserves_expected_behavior(self):
        broken = independent_acceptance(self.project)
        self.assertFalse(broken["passed"])
        self.assertIsNone(broken["execution_error"])
        path = self.project / "app.py"
        path.write_text(path.read_text().replace('"fields": ["title"]', '"fields": ["title", "description"]'))
        repaired = independent_acceptance(self.project)
        self.assertTrue(repaired["passed"])
        self.assertEqual([row["query"] for row in repaired["observations"]],
                         ["blue", "export", "MILK", "does-not-exist"])

    def test_independent_oracle_timeout_is_bounded_and_structured(self):
        (self.project / "app.py").write_text("import time\ntime.sleep(5)\n")
        started = time.monotonic()
        outcome = independent_acceptance(self.project, timeout=.1)
        self.assertLess(time.monotonic() - started, 1)
        self.assertFalse(outcome["passed"])
        self.assertEqual(outcome["execution_error"], "oracle_timeout")

    def test_independent_oracle_crash_cannot_exit_parent_or_pass(self):
        for source, reason in [("import sys; sys.exit(0)", "oracle_execution_error:SystemExit"),
                               ("import os; os._exit(0)", "invalid_oracle_result_protocol"),
                               ("import os; os._exit(7)", "oracle_process_failed"),
                               ("invalid python !!!", "oracle_execution_error:SyntaxError")]:
            with self.subTest(source=source):
                (self.project / "app.py").write_text(source)
                outcome = independent_acceptance(self.project)
                self.assertFalse(outcome["passed"])
                self.assertEqual(outcome["execution_error"], reason)

    def test_independent_oracle_does_not_inherit_credentials(self):
        path = self.project / "app.py"
        source = path.read_text().replace('"fields": ["title"]', '"fields": ["title", "description"]')
        path.write_text("import os\nassert not any(k in os.environ for k in ('TYPESAFE_API_KEY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'PRIVATE_TEST_SECRET'))\nos.environ['ORACLE_CHILD_ONLY'] = 'set'\n" + source)
        credentials = {key: "synthetic-test-secret" for key in
                       ("TYPESAFE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PRIVATE_TEST_SECRET")}
        with patch.dict(os.environ, credentials):
            outcome = independent_acceptance(self.project)
        self.assertTrue(outcome["passed"], outcome)
        self.assertNotIn("ORACLE_CHILD_ONLY", os.environ)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "run.py"), *args],
                              capture_output=True, text=True, timeout=15)

    def test_loop_repair_and_replay_divergence(self):
        out = self.directory / "run"
        result = self.cli("loop", "--out", str(out))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        outcome = json.loads((out / "result.json").read_text())
        self.assertEqual((outcome["checks_executed"], outcome["worker_iterations"], outcome["remote_jev_requests"]), (5, 1, 0))
        matched = self.cli("replay", "--run", str(out))
        self.assertEqual(json.loads(matched.stdout)["status"], "matched")
        changed = dict(self.policy, max_checks=1)
        policy_file = self.directory / "changed-policy.json"
        policy_file.write_text(json.dumps(changed))
        replay = self.cli("replay", "--run", str(out), "--policy", str(policy_file))
        self.assertEqual(replay.returncode, 2)
        self.assertEqual(json.loads(replay.stdout)["status"], "diverged")

    def test_stalled_loop_stops_without_false_complete(self):
        out = self.directory / "stalled"
        result = self.cli("loop", "--case", "stalled", "--out", str(out))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads((out / "result.json").read_text())["reason"], "no_new_evidence_or_source_change")

    def test_correct_loop_needs_no_worker(self):
        out = self.directory / "correct"
        self.assertEqual(self.cli("loop", "--case", "correct", "--out", str(out)).returncode, 0)
        self.assertEqual(json.loads((out / "result.json").read_text())["worker_iterations"], 0)

    def test_fixed_baseline_has_no_model_calls(self):
        out = self.directory / "fixed"
        self.assertEqual(self.cli("loop", "--selector", "fixed", "--out", str(out)).returncode, 0)
        self.assertEqual(json.loads((out / "result.json").read_text())["judge_invocations"], 0)


if __name__ == "__main__":
    unittest.main()
