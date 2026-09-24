"""Boundary checks for real child processes and persisted agent data."""
import asyncio
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from jev_agent.runtime import CodexRunner, RuntimeFailure, clean, process, worker_environment
from jev_agent.core import Session


class FixtureJudge:
    """Deterministic test transport; never accesses TypeSafe."""
    def __init__(self, route="implement", action="finish"):
        self.route = route
        self.action = action
        self.calls = []

    async def ask(self, state, questions, directory, emit, cancel_event):
        self.calls.append(state)
        answers = {}
        for key, question in questions.items():
            if question["type"] == "noul":
                answers[key] = {"type": "noul", "noul": 1.0}
            else:
                selected = self.route if key == "route" else "code" if key == "category" else self.action
                answers[key] = {"type": "choice", "choice": selected,
                                "confidence": 1.0,
                                "probabilities": {k: float(k == selected) for k in question["criteria"]}}
        return {"model": "fixture-only", "answers": answers,
                "usage": {"input_tokens": 5, "output_tokens": 2}}


class FixtureRunner:
    """Deterministic test worker; optional action mutates a temporary workspace."""
    def __init__(self, action=None, text="Prepared response.", usage=None):
        self.action = action
        self.text = text
        self.usage = usage if usage is not None else {"input_tokens": 11, "output_tokens": 3}
        self.calls = []

    async def run(self, prompt, workspace, directory, emit, cancel_event,
                  readonly=False, schema=None):
        self.calls.append({"prompt": prompt, "readonly": readonly})
        if self.action:
            self.action(workspace)
        return {"text": self.text, "usage": self.usage, "completed": True}


class WaitingRunner(FixtureRunner):
    def __init__(self):
        super().__init__()
        self.started = asyncio.Event()

    async def run(self, prompt, workspace, directory, emit, cancel_event,
                  readonly=False, schema=None):
        self.started.set()
        await cancel_event.wait()
        raise asyncio.CancelledError()


class RedactionTests(unittest.TestCase):
    def test_nested_secrets_and_terminal_control_sequences_are_removed(self):
        value = {
            "Authorization": "Bearer example-secret",
            "nested": [{"api_key": "private-value"}],
            "output": "\x1b[31mred\x1b[0m \x1b]0;malicious title\x07"
                      "Bearer other-secret apikey_dummy_secret_for_test",
        }
        result = clean(value)
        self.assertEqual(result["Authorization"], "[redacted]")
        self.assertEqual(result["nested"][0]["api_key"], "[redacted]")
        self.assertNotIn("\x1b", result["output"])
        self.assertNotIn("malicious title", result["output"])
        self.assertNotIn("other-secret", result["output"])
        self.assertNotIn("apikey_dummy", result["output"])
        self.assertIn("red", result["output"])

    def test_worker_does_not_inherit_provider_secrets(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "private-value",
                                    "OPENAI_API_KEY": "another-value",
                                    "GITHUB_TOKEN": "third-value",
                                    "PATH": "/usr/bin:/bin"}, clear=True):
            environment = worker_environment()
        self.assertNotIn("TYPESAFE_API_KEY", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("GITHUB_TOKEN", environment)
        self.assertEqual(environment["PATH"], "/usr/bin:/bin")


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def test_both_output_streams_and_exit_status_are_preserved(self):
        observed = []
        result = await process(
            [sys.executable, "-c", "import sys; print('out'); print('err',file=sys.stderr); sys.exit(7)"],
            cwd=self.directory, cancel_event=asyncio.Event(), timeout=2,
            on_line=lambda stream, line: observed.append((stream, line.strip())),
        )
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["stdout"], "out\n")
        self.assertEqual(result["stderr"], "err\n")
        self.assertCountEqual(observed, [("stdout", "out"), ("stderr", "err")])

    async def test_pre_cancelled_call_never_starts_a_process(self):
        marker = self.directory / "should-not-exist"
        cancel = asyncio.Event()
        cancel.set()
        with self.assertRaises(asyncio.CancelledError):
            await process(
                [sys.executable, "-c", "from pathlib import Path; Path(%r).touch()" % str(marker)],
                cwd=self.directory, cancel_event=cancel, timeout=2,
            )
        self.assertFalse(marker.exists())

    async def test_output_limit_is_detected_before_process_timeout(self):
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeFailure, "Process output exceeded the limit"):
            await process(
                [sys.executable, "-c", "import time; print('x'*200,flush=True); time.sleep(5)"],
                cwd=self.directory, cancel_event=asyncio.Event(), timeout=1,
                max_bytes=100,
            )
        self.assertLess(time.monotonic() - started, 0.8)

    async def test_stream_parser_error_stops_process_immediately(self):
        def rejected_line(stream, line):
            raise RuntimeFailure("invalid provider event")

        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeFailure, "invalid provider event"):
            await process(
                [sys.executable, "-c", "import time; print('bad event',flush=True); time.sleep(5)"],
                cwd=self.directory, cancel_event=asyncio.Event(), timeout=1,
                on_line=rejected_line,
            )
        self.assertLess(time.monotonic() - started, 0.8)

    async def test_successful_group_kill_is_not_repeated_or_parser_error_masked(self):
        real_killpg = os.killpg
        calls = []

        def kill_once(pid, sig):
            calls.append((pid, sig))
            if len(calls) > 1:
                raise PermissionError("process group is no longer owned")
            return real_killpg(pid, sig)

        def rejected_line(stream, line):
            raise RuntimeFailure("invalid provider event")

        with patch("jev_agent.runtime.os.killpg", side_effect=kill_once):
            with self.assertRaisesRegex(RuntimeFailure, "invalid provider event"):
                await process(
                    [sys.executable, "-c", "import time; print('bad event',flush=True); time.sleep(5)"],
                    cwd=self.directory, cancel_event=asyncio.Event(), timeout=1,
                    on_line=rejected_line,
                )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], signal.SIGKILL)

    async def test_failed_first_group_kill_propagates_and_cleanup_retries(self):
        real_killpg = os.killpg
        calls = []

        def fail_first_kill(pid, sig):
            calls.append((pid, sig))
            if len(calls) == 1:
                raise PermissionError("first group signal denied")
            return real_killpg(pid, sig)

        def rejected_line(stream, line):
            raise RuntimeFailure("invalid provider event")

        with patch("jev_agent.runtime.os.killpg", side_effect=fail_first_kill):
            with self.assertRaisesRegex(PermissionError, "first group signal denied"):
                await process(
                    [sys.executable, "-c", "import time; print('bad event',flush=True); time.sleep(5)"],
                    cwd=self.directory, cancel_event=asyncio.Event(), timeout=1,
                    on_line=rejected_line,
                )
        # The second cleanup call really kills the child; no process is left
        # behind, and the original permission failure is still observable.
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], calls[1])

    async def test_cancellation_stops_descendant_process(self):
        heartbeat = self.directory / "heartbeat.txt"
        child_pid_file = self.directory / "child.pid"
        child_script = (
            "import time\n"
            "while True:\n"
            "    with open(%r,'a') as f: f.write('tick\\n')\n"
            "    time.sleep(0.03)\n" % str(heartbeat)
        )
        parent_script = (
            "import pathlib,subprocess,sys,time\n"
            "child=subprocess.Popen([sys.executable,'-c',%r])\n"
            "pathlib.Path(%r).write_text(str(child.pid))\n"
            "print('ready',flush=True)\n"
            "time.sleep(30)\n" % (child_script, str(child_pid_file))
        )
        cancel, ready = asyncio.Event(), asyncio.Event()

        def line(stream, text):
            if text.strip() == "ready":
                ready.set()

        task = asyncio.create_task(process(
            [sys.executable, "-c", parent_script], cwd=self.directory,
            cancel_event=cancel, timeout=3, on_line=line,
        ))
        try:
            await asyncio.wait_for(ready.wait(), timeout=2)
            for _ in range(30):
                if heartbeat.exists():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(heartbeat.exists(), "descendant must really execute before cancellation")
            cancel.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=1)
            size_after_cancel = heartbeat.stat().st_size
            await asyncio.sleep(0.12)
            self.assertEqual(heartbeat.stat().st_size, size_after_cancel)
        finally:
            cancel.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if child_pid_file.exists():
                with contextlib.suppress(ProcessLookupError):
                    os.kill(int(child_pid_file.read_text()), signal.SIGKILL)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.session = Session.create(self.base / "sessions")
        self.session.judge = FixtureJudge()
        self.session.runner = FixtureRunner()

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def test_worker_claim_is_not_independent_acceptance(self):
        self.session.runner.text = "Everything is correct. All acceptance tests passed."
        result = await self.session.run_turn("Create a tool.")
        self.assertEqual(result["status"], "ready")
        self.assertIn("without_independent_acceptance", result["reason"])
        self.assertEqual(result["meters"]["checks"], 0)
        self.assertFalse(self.session.busy)
        persisted = json.loads((self.session.directory / "turn-001" / "result.json").read_text())
        self.assertEqual(persisted["status"], "ready")

    async def test_conversation_uses_readonly_worker_and_resumes_after_relocation(self):
        self.session.judge.route = "answer"
        result = await self.session.run_turn("Explain the design in Russian.")
        self.assertEqual(result["status"], "answered")
        self.assertTrue(self.session.runner.calls[0]["readonly"])
        target = self.base / "moved-session"
        shutil.copytree(self.session.directory, target)
        shutil.rmtree(self.session.directory)
        resumed = Session.load(target)
        self.assertEqual(resumed.workspace, (target / "workspace").resolve())
        self.assertEqual(len(resumed.history), 2)
        resumed.judge = FixtureJudge(route="answer")
        resumed.runner = FixtureRunner()
        second = await resumed.run_turn("Now explain the tradeoffs.")
        self.assertEqual(second["turn"], 2)
        self.assertIn("Explain the design in Russian.", resumed.runner.calls[0]["prompt"])
        self.assertEqual(len(resumed.history), 4)
        sequences = [e["seq"] for e in resumed.events()]
        self.assertEqual(sequences, sorted(set(sequences)))

    async def test_failed_registered_check_overrides_confident_finish(self):
        self.session.checks = [{"id": "fails", "title": "Fails deliberately",
                                "argv": [sys.executable, "-c", "raise SystemExit(1)"],
                                "origin": "registered"}]
        result = await self.session.run_turn("Repair this project.")
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(result["reason"], "checks_failed_or_no_progress")
        self.assertEqual(result["meters"]["checks"], 2)
        self.assertEqual(len(self.session.runner.calls), 1)

    async def test_registered_check_really_runs_again_after_file_change(self):
        (self.session.workspace / "value.txt").write_text("broken")
        self.session.checks = [{"id": "correct-value", "title": "Known value is fixed",
                                "argv": [sys.executable, "-c", "from pathlib import Path; assert Path('value.txt').read_text() == 'fixed'"],
                                "origin": "registered"}]
        self.session.runner.action = lambda workspace: (workspace / "value.txt").write_text("fixed")
        result = await self.session.run_turn("Fix the known value.")
        self.assertEqual(result["status"], "accepted")
        initial = json.loads((self.session.directory / "turn-001" / "baseline-checks.json").read_text())
        final = json.loads((self.session.directory / "turn-001" / "attempt-01-checks.json").read_text())
        self.assertEqual(initial["passed"], 0)
        self.assertEqual(final["passed"], 1)
        self.assertTrue(final["fresh"])
        self.assertNotEqual(initial["snapshot"], final["snapshot"])

    async def test_mission_checks_follow_a_relocated_session_workspace(self):
        original = Session.create(self.base / "mission-sessions", mission="loglab")
        moved = self.base / "moved-mission"
        shutil.copytree(original.directory, moved)
        shutil.rmtree(original.directory)
        resumed = Session.load(moved)
        for check in resumed.checks:
            with self.subTest(check=check["id"]):
                project_argument = check["argv"].index("--project") + 1
                self.assertEqual(Path(check["argv"][project_argument]), resumed.workspace)

    async def test_a_check_that_changes_its_snapshot_cannot_accept(self):
        (self.session.workspace / "counter.txt").write_text("0")
        script = ("from pathlib import Path; p=Path('counter.txt'); "
                  "p.write_text(str(int(p.read_text())+1))")
        self.session.checks = [{"id": "mutating-check", "title": "Mutates source",
                                "argv": [sys.executable, "-c", script], "origin": "registered"}]
        result = await self.session.run_turn("Repair this project.")
        self.assertEqual(result["status"], "stopped")
        report = json.loads((self.session.directory / "turn-001" / "attempt-01-checks.json").read_text())
        self.assertEqual(report["passed"], 1)
        self.assertFalse(report["fresh"])

    async def test_worker_cannot_weaken_registered_check_to_gain_acceptance(self):
        project = self.base / "registered-project"
        project.mkdir()
        (project / "oracle.py").write_text("raise SystemExit(1)\n")
        (project / "jev-checks.json").write_text(json.dumps({"checks": [
            {"id": "oracle", "argv": [sys.executable, "-B", "oracle.py"]}
        ]}))
        session = Session.create(self.base / "protected-sessions", project=project)
        session.judge = FixtureJudge()
        session.runner = FixtureRunner(action=lambda workspace: (workspace / "oracle.py").write_text("raise SystemExit(0)\n"))
        result = await session.run_turn("Repair the failing project.")
        self.assertEqual(result["status"], "error")
        self.assertIn("The check contract changed", result["summary"])
        self.assertEqual(result["meters"]["checks"], 1, "only the original failing check may execute")

    async def test_root_level_generated_tests_are_executed_but_not_independent(self):
        def create_test(workspace):
            (workspace / "test_root.py").write_text(
                "import unittest\nclass Generated(unittest.TestCase):\n"
                "    def test_result(self): self.assertEqual(2+2,4)\n")
        self.session.runner.action = create_test
        result = await self.session.run_turn("Create a project with tests at its root.")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["meters"]["checks"], 1)
        report = json.loads((self.session.directory / "turn-001" / "attempt-01-checks.json").read_text())
        self.assertIn("Ran 1 test", report["items"][0]["output"])
        self.assertFalse(report["registered"])

    async def test_worker_generated_tests_cannot_become_independent_acceptance(self):
        def create_test(workspace):
            (workspace / "tests").mkdir()
            (workspace / "tests" / "test_generated.py").write_text(
                "import unittest\nclass Generated(unittest.TestCase):\n"
                "    def test_result(self): self.assertEqual(2+2,4)\n")

        self.session.runner.action = create_test
        result = await self.session.run_turn("Build a thing and tests.")
        self.assertEqual(result["status"], "ready")
        report = json.loads((self.session.directory / "turn-001" / "attempt-01-checks.json").read_text())
        self.assertEqual(report["passed"], 1)
        self.assertFalse(report["registered"])
        self.assertEqual(report["items"][0]["origin"], "worker_generated")

    async def test_no_tests_found_is_not_a_passing_check(self):
        (self.session.workspace / "tests").mkdir()
        (self.session.workspace / "tests" / "test_empty.py").write_text("# No actual tests\n")
        result = await self.session.run_turn("Check my project.")
        self.assertEqual(result["status"], "stopped")
        report = json.loads((self.session.directory / "turn-001" / "attempt-01-checks.json").read_text())
        self.assertEqual(report["passed"], 0)

    async def test_malformed_jev_response_is_an_error_not_a_worker_run(self):
        class BrokenJudge:
            async def ask(self, *args, **kwargs):
                return {"model": "fixture-only", "answers": {},
                        "usage": {"input_tokens": 5, "output_tokens": 1}}

        self.session.judge = BrokenJudge()
        result = await self.session.run_turn("Build a tool.")
        self.assertEqual(result["status"], "error")
        self.assertFalse(self.session.busy)
        self.assertEqual(self.session.runner.calls, [])
        self.assertFalse(result["meters"]["usage_complete"])
        self.assertTrue((self.session.directory / "turn-001" / "result.json").is_file())

    async def test_provider_error_is_redacted_and_next_turn_can_run(self):
        secret = "apikey_dummy_secret_only_for_unit_test"

        class ErrorJudge:
            async def ask(self, *args, **kwargs):
                raise RuntimeFailure("Provider rejected " + secret)

        self.session.judge = ErrorJudge()
        result = await self.session.run_turn("Do work.")
        self.assertEqual(result["status"], "error")
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, (self.session.directory / "events.jsonl").read_text())
        self.session.judge = FixtureJudge(route="answer")
        followup = await self.session.run_turn("Explain the error.")
        self.assertEqual(followup["status"], "answered")

    async def test_concurrent_turn_rejected_and_cancelled_turn_is_persisted(self):
        runner = WaitingRunner()
        self.session.runner = runner
        task = asyncio.create_task(self.session.run_turn("Implement this."))
        await asyncio.wait_for(runner.started.wait(), timeout=1)
        try:
            self.assertTrue(self.session.busy)
            meters = [event["data"] for event in self.session.events() if event["type"] == "meters"]
            self.assertEqual(meters[-1]["worker_calls"], 1, "a running attempt is visible before it completes")
            with self.assertRaises(ValueError):
                await self.session.run_turn("Overlapping request.")
            self.session.cancel()
            result = await asyncio.wait_for(task, timeout=1)
        finally:
            self.session.cancel()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(self.session.busy)
        self.assertFalse(result["meters"]["usage_complete"])
        persisted = json.loads((self.session.directory / "turn-001" / "result.json").read_text())
        self.assertEqual(persisted["status"], "cancelled")
        self.session.runner = FixtureRunner()
        self.session.judge = FixtureJudge(route="answer")
        self.assertEqual((await self.session.run_turn("Continue with an explanation."))["status"], "answered")

    async def test_bad_display_callback_cannot_lock_session(self):
        def broken_display(event):
            raise RuntimeError("Display failed")

        result = await self.session.run_turn("Create a tool.", emit=broken_display)
        self.assertEqual(result["status"], "ready")
        self.assertFalse(self.session.busy)
        self.assertEqual(self.session.events()[-1]["type"], "end")

    async def test_invalid_worker_usage_does_not_create_false_counters(self):
        for usage in ({"input_tokens": True, "output_tokens": 3},
                      {"input_tokens": -10, "output_tokens": 3},
                      {"input_tokens": 1}):
            with self.subTest(usage=usage):
                self.session.runner.usage = usage
                result = await self.session.run_turn("Build a tool.")
                self.assertEqual(result["status"], "ready")
                self.assertFalse(result["meters"]["usage_complete"])
                self.assertEqual(result["meters"]["worker_tokens"], 0)

    async def test_custom_runner_secret_is_not_returned_or_kept_in_history(self):
        secret = "apikey_dummy_secret_only_for_unit_test"
        self.session.runner.text = "Result with accidental credential " + secret
        result = await self.session.run_turn("Build a tool.")
        self.assertNotIn(secret, result["summary"])
        self.assertNotIn(secret, json.dumps(self.session.history))

    async def test_oversized_or_empty_input_leaves_session_idle(self):
        for prompt in ("  ", "x" * 20001, None):
            with self.subTest(prompt_type=type(prompt).__name__):
                with self.assertRaises(ValueError):
                    await self.session.run_turn(prompt)
                self.assertFalse(self.session.busy)

    async def test_settings_are_validated_atomic_persisted_and_idle_only(self):
        self.session.configure(execution_mode="plan", jev_mode="off")
        restored = Session.load(self.session.directory)
        self.assertEqual(restored.status()["execution_mode"], "plan")
        self.assertEqual(restored.status()["jev_mode"], "off")
        with self.assertRaises(ValueError):
            self.session.configure(execution_mode="auto", jev_mode="bogus")
        self.assertEqual(self.session.execution_mode, "plan")
        self.session.busy = True
        with self.assertRaises(ValueError):
            self.session.configure(jev_mode="assist")
        self.session.busy = False

    async def test_resume_activates_selected_session_but_readonly_load_does_not(self):
        second = Session.create(self.base / "sessions")
        pointer = self.base / "sessions" / "last-session.txt"
        self.assertEqual(pointer.read_text(), second.id)
        Session.load(self.session.directory, activate=False)
        self.assertEqual(pointer.read_text(), second.id)
        Session.load(self.session.directory)
        self.assertEqual(pointer.read_text(), self.session.id)
        renamed = self.session.directory.with_name("portable-copy")
        self.session.directory.rename(renamed)
        Session.load(renamed)
        self.assertEqual(pointer.read_text(), "portable-copy")
        self.assertEqual(Session.load(pointer.parent / pointer.read_text()).id, self.session.id)

    async def test_malformed_event_shapes_are_skipped_without_lock_or_duplicate_sequence(self):
        rows = [42, None, [], {"seq": 100, "turn": "bad", "type": "bad", "data": {}},
                {"seq": 10, "turn": 2, "type": "message", "data": {"text": "Saved"}}]
        (self.session.directory / "events.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n{")
        resumed = Session.load(self.session.directory)
        resumed.runner, resumed.judge = FixtureRunner(), FixtureJudge()
        result = await resumed.run_turn("Create a tool.")
        self.assertEqual(result["status"], "ready")
        self.assertFalse(resumed.busy)
        self.assertEqual(result["turn"], 3)
        self.assertEqual(resumed.events()[1]["seq"], 11)

    async def test_existing_orphan_turn_directory_recovers_without_lock(self):
        (self.session.directory / "turn-001").mkdir()
        result = await self.session.run_turn("Create a tool.")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["turn"], 2)
        self.assertFalse(self.session.busy)

    async def test_plan_forces_readonly_in_every_jev_mode_and_does_not_run_checks(self):
        self.session.checks = [{"id": "unsafe-for-plan", "argv": [sys.executable, "-c", "raise SystemExit(1)"]}]
        for mode in ("assist", "observe", "off"):
            self.session.configure(execution_mode="plan", jev_mode=mode)
            result = await self.session.run_turn("Create files now.")
            self.assertEqual(result["status"], "answered")
            self.assertTrue(self.session.runner.calls[-1]["readonly"])
            self.assertEqual(result["meters"]["checks"], 0)

    async def test_plan_detects_mutation_even_if_injected_worker_ignores_readonly(self):
        self.session.configure(execution_mode="plan", jev_mode="off")
        self.session.runner.action = lambda workspace: (workspace / "app.py").write_text("changed")
        result = await self.session.run_turn("Plan a change.")
        self.assertEqual(result["status"], "error")
        self.assertIn("read-only turn", result["summary"])

    async def test_off_calls_no_judge_and_failed_checks_still_block_completion(self):
        self.session.configure(jev_mode="off")
        self.session.checks = [{"id": "failure", "title": "failure", "argv": [sys.executable, "-c", "raise SystemExit(1)"]}]
        result = await self.session.run_turn("Fix the problem.")
        self.assertEqual(result["status"], "stopped")
        self.assertEqual(self.session.judge.calls, [])
        self.assertEqual(result["meters"]["jev_calls"], 0)
        self.assertTrue(any("Jev off" in e["data"].get("text", "") for e in self.session.events()))

    async def test_observe_records_but_does_not_use_route_or_review(self):
        self.session.configure(jev_mode="observe")
        self.session.judge = FixtureJudge(route="answer", action="ask_user")
        result = await self.session.run_turn("Create a tool.")
        self.assertEqual(result["status"], "ready")
        self.assertFalse(self.session.runner.calls[0]["readonly"])
        self.assertEqual(len(self.session.judge.calls), 2)
        decisions = [e for e in self.session.events() if e["type"] == "jev"]
        self.assertTrue(all(not e["data"]["applied"] for e in decisions))

    async def test_observe_provider_failure_falls_back_with_incomplete_usage(self):
        class UnavailableJudge:
            async def ask(self, *args, **kwargs):
                raise RuntimeFailure("unavailable")
        self.session.configure(jev_mode="observe")
        self.session.judge = UnavailableJudge()
        result = await self.session.run_turn("Create a tool.")
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["meters"]["usage_complete"])
        self.assertEqual(result["meters"]["jev_calls"], 2)

    async def test_failed_attempt_triage_reaches_next_worker_without_overriding_checks(self):
        (self.session.workspace / "value.txt").write_text("broken")
        self.session.checks = [{"id": "value", "title": "value", "argv": [sys.executable, "-c",
                                "from pathlib import Path; assert Path('value.txt').read_text() == 'fixed'"]}]
        calls = []
        def change(workspace):
            calls.append(True)
            (workspace / "value.txt").write_text("still broken" if len(calls) == 1 else "fixed")
        self.session.runner.action = change
        result = await self.session.run_turn("Repair value.")
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(self.session.runner.calls), 2)
        context = json.loads(self.session.runner.calls[1]["prompt"].split("\n\n", 1)[1])
        self.assertEqual(context["failure_triage"]["category"], "code")
        self.assertFalse(context["failure_triage"]["verified_root_cause"])
        self.assertEqual(context["verification"]["passed"], 0)
        snippet = next(item for item in context["source_snippets"] if item["path"] == "value.txt")
        self.assertEqual(snippet["excerpt"].strip(), "still broken")
        self.assertEqual(snippet["sha256"], hashlib.sha256(b"still broken").hexdigest())
        first_context = json.loads((self.session.directory / "turn-001" / "attempt-01-context.json").read_text())
        second_context = json.loads((self.session.directory / "turn-001" / "attempt-02-context.json").read_text())
        self.assertEqual(first_context["attempt"], 1)
        self.assertEqual(second_context["attempt"], 2)
        self.assertNotEqual(first_context["candidates"][0]["sha256"], second_context["candidates"][0]["sha256"])
        self.assertTrue(any(e["type"] == "jev" and e["data"]["purpose"] == "triage" for e in self.session.events()))

    async def test_failed_worker_attempt_is_counted_with_unknown_usage(self):
        class FailedRunner(FixtureRunner):
            async def run(self, *args, **kwargs):
                raise RuntimeFailure("worker unavailable")
        self.session.runner = FailedRunner()
        result = await self.session.run_turn("Create a tool.")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["meters"]["worker_calls"], 1)
        self.assertFalse(result["meters"]["usage_complete"])
        start = next(e for e in self.session.events() if e["type"] == "meters" and e["data"]["worker_calls"] == 1)
        failure = next(e for e in self.session.events() if e["type"] == "error")
        self.assertLess(start["seq"], failure["seq"])

    async def test_context_ranking_applies_only_in_assist(self):
        class RankJudge(FixtureJudge):
            async def ask(self, state, questions, *args):
                result = await super().ask(state, questions, *args)
                if "candidates" in state:
                    for key in result["answers"]:
                        result["answers"][key]["noul"] = 0.9 if state["candidates"][key]["path"] == "z.py" else 0.1
                return result
        for name in ("a.py", "z.py"):
            (self.session.workspace / name).write_text("needle = 1\n")
        self.session.judge = RankJudge()
        for mode, expected in (("assist", "z.py"), ("observe", "a.py"), ("off", "a.py")):
            self.session.configure(jev_mode=mode)
            result = await self.session.run_turn("Inspect needle.")
            self.assertNotEqual(result["status"], "error")
            context = json.loads(self.session.runner.calls[-1]["prompt"].split("\n\n", 1)[1])
            self.assertEqual(context["source_snippets"][0]["path"], expected)
            self.assertEqual("relevance" in context["source_snippets"][0], mode == "assist")

    async def test_low_confidence_triage_is_recorded_as_unapplied(self):
        class LowConfidenceJudge(FixtureJudge):
            async def ask(self, state, questions, *args):
                result = await super().ask(state, questions, *args)
                result["answers"]["category"]["confidence"] = 0.2
                return result
        self.session.judge = LowConfidenceJudge()
        report = {"items": [{"id": "broken", "passed": False, "exit_code": 1, "output": "Assertion failed"}], "fresh": True}
        advice = await self.session.triage_failure("Repair this.", report, self.session.directory)
        self.assertIsNone(advice)
        decision = next(e for e in self.session.events() if e["type"] == "jev")
        self.assertFalse(decision["data"]["applied"])

    async def test_check_and_provider_lifecycle_use_stable_real_ids(self):
        self.session.checks = [{"id": "ok", "title": "ok", "argv": [sys.executable, "-c", "print('pass')"]}]
        await self.session.run_turn("Implement this.")
        events = [e["data"] for e in self.session.events() if e["type"] == "tool"]
        self.assertEqual(events[0]["call_id"], events[1]["call_id"])
        self.assertNotEqual(events[0]["call_id"], events[2]["call_id"])
        self.assertEqual(events[0]["lifecycle"], "started")
        self.assertEqual(events[1]["lifecycle"], "completed")
        observed = []
        async def fake_process(argv, **kwargs):
            for kind, status in (("item.started", "in_progress"), ("item.completed", "completed")):
                kwargs["on_line"]("stdout", json.dumps({"type": kind, "item": {
                    "type": "command_execution", "id": "item_7", "command": "python app.py", "status": status}}))
            kwargs["on_line"]("stdout", json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "Done."}}))
            kwargs["on_line"]("stdout", json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}))
            return {"exit_code": 0, "stderr": ""}
        with patch("jev_agent.runtime.process", fake_process), patch("jev_agent.runtime.codex_binary", return_value="codex"):
            await CodexRunner().run("test", self.session.workspace, self.session.directory / "worker-01",
                                    lambda event_type, **data: observed.append((event_type, data)), asyncio.Event())
        tools = [data for kind, data in observed if kind == "tool"]
        self.assertEqual(tools[0]["item_id"], "item_7")
        self.assertEqual(tools[0]["call_id"], tools[1]["call_id"])
        self.assertEqual([e["lifecycle"] for e in tools], ["started", "completed"])

    async def test_provider_failure_is_reported_in_the_providers_own_words(self):
        # A usage limit or an auth failure arrives on the event stream and never
        # reaches stderr, so the old message pointed at an empty stderr.txt.
        limit = "You've hit your usage limit. Try again at Sep 26th."
        async def fake_process(argv, **kwargs):
            kwargs["on_line"]("stdout", json.dumps({"type": "turn.failed", "error": {"message": limit}}))
            return {"exit_code": 1, "stderr": ""}
        directory = self.session.directory / "worker-limit"
        with patch("jev_agent.runtime.process", fake_process), patch("jev_agent.runtime.codex_binary", return_value="codex"):
            with self.assertRaises(RuntimeFailure) as caught:
                await CodexRunner().run("test", self.session.workspace, directory,
                                        lambda *a, **k: None, asyncio.Event())
        self.assertIn(limit, str(caught.exception))
        self.assertEqual((directory / "stderr.txt").read_text(), "")

    async def test_a_failure_without_a_provider_message_still_names_the_log(self):
        async def fake_process(argv, **kwargs):
            return {"exit_code": 1, "stderr": ""}
        directory = self.session.directory / "worker-silent"
        with patch("jev_agent.runtime.process", fake_process), patch("jev_agent.runtime.codex_binary", return_value="codex"):
            with self.assertRaises(RuntimeFailure) as caught:
                await CodexRunner().run("test", self.session.workspace, directory,
                                        lambda *a, **k: None, asyncio.Event())
        self.assertIn("stderr.txt", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
