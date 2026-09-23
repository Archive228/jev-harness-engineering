"""Claude Code as the worker: the stream shapes below were captured from a real run."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jev_agent.core import Session
from jev_agent.runtime import ClaudeRunner, RuntimeFailure, claude_binary


def assistant(*blocks):
    return json.dumps({"type": "assistant", "message": {"content": list(blocks)}})


def user(*blocks):
    return json.dumps({"type": "user", "message": {"content": list(blocks)}})


def result(**fields):
    base = {"type": "result", "is_error": False, "subtype": "success",
            "terminal_reason": "completed", "result": "Готово.",
            "usage": {"input_tokens": 4, "output_tokens": 81,
                      "cache_read_input_tokens": 7579, "cache_creation_input_tokens": 1690},
            "total_cost_usd": 0.0166718, "num_turns": 2, "permission_denials": []}
    base.update(fields)
    return json.dumps(base)


HAPPY = [
    json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5-5[1m]"}),
    assistant({"type": "tool_use", "id": "toolu_01", "name": "Read",
               "input": {"file_path": "data.txt"}}),
    json.dumps({"type": "rate_limit_event"}),              # Undocumented, must not break us.
    json.dumps({"type": "system", "subtype": "task_summary"}),
    user({"type": "tool_result", "tool_use_id": "toolu_01", "content": "1\tALPHA=1"}),
    assistant({"type": "text", "text": "Ключи: ALPHA, BETA."}),
    result(),
    json.dumps({"type": "system", "subtype": "post_turn_summary"}),  # Arrives after result.
]


class StreamHarness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "ws"
        self.workspace.mkdir()
        self.directory = Path(self.temporary.name) / "turn-001" / "worker-01"
        self.events = []
        self.argv = None

    async def asyncTearDown(self):
        self.temporary.cleanup()

    def _process(self, lines, exit_code=0, stderr=""):
        async def fake(argv, **kwargs):
            self.argv = [str(a) for a in argv]
            for line in lines:
                kwargs["on_line"]("stdout", line)
            return {"exit_code": exit_code, "stderr": stderr, "stdout": "", "elapsed_ms": 12.0}
        return fake

    async def _run(self, lines, exit_code=0, stderr="", **kwargs):
        with patch("jev_agent.runtime.process", self._process(lines, exit_code, stderr)), \
                patch("jev_agent.runtime.claude_binary", return_value="claude"):
            return await ClaudeRunner().run(
                "задача", self.workspace, self.directory,
                lambda event_type, **data: self.events.append((event_type, data)),
                asyncio.Event(), **kwargs)

    def _of(self, kind):
        return [data for name, data in self.events if name == kind]


class HappyPathTests(StreamHarness):
    async def test_a_finished_turn_returns_its_text_and_usage(self):
        output = await self._run(HAPPY)
        self.assertEqual(output["text"], "Готово.")
        self.assertTrue(output["completed"])
        # Cached input is still input; otherwise a long turn reads as almost free.
        self.assertEqual(output["usage"], {"input_tokens": 4 + 7579 + 1690, "output_tokens": 81})

    async def test_a_tool_call_opens_and_closes_one_card(self):
        await self._run(HAPPY)
        tools = self._of("tool")
        self.assertEqual([t["lifecycle"] for t in tools], ["started", "completed"])
        self.assertEqual(tools[0]["call_id"], tools[1]["call_id"])
        self.assertEqual(tools[0]["item_id"], "toolu_01")
        self.assertEqual(tools[0]["kind"], "read")
        self.assertEqual(tools[0]["command"], "data.txt")
        self.assertEqual(tools[1]["status"], "completed")
        self.assertEqual(tools[1]["exit_code"], 0)
        # The prefix keeps separate attempts from sharing a card.
        self.assertTrue(tools[0]["call_id"].startswith("turn-001:worker-01:"))

    async def test_assistant_text_reaches_the_conversation(self):
        await self._run(HAPPY)
        self.assertEqual(self._of("message")[-1]["text"], "Ключи: ALPHA, BETA.")

    async def test_the_artifacts_a_turn_leaves_behind_are_all_written(self):
        await self._run(HAPPY)
        for name in ("prompt.txt", "stderr.txt", "events.jsonl", "final.txt"):
            self.assertTrue((self.directory / name).is_file(), name)
        recorded = (self.directory / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(recorded), len(HAPPY))  # Everything is kept, even what the UI ignored.

    async def test_an_unknown_event_type_is_recorded_rather_than_fatal(self):
        await self._run([json.dumps({"type": "something_new_in_a_later_version"})] + HAPPY)
        self.assertEqual(self._of("message")[-1]["text"], "Ключи: ALPHA, BETA.")

    async def test_a_broken_line_means_a_broken_stream(self):
        with self.assertRaises(RuntimeFailure) as caught:
            await self._run(["{not json"])
        self.assertIn("повреждённый", str(caught.exception))


class ToolMappingTests(StreamHarness):
    async def test_a_todo_list_becomes_a_plan_not_a_tool_card(self):
        await self._run([assistant({"type": "tool_use", "id": "toolu_t", "name": "TodoWrite",
                                    "input": {"todos": [{"content": "Шаг один", "status": "completed"},
                                                        {"content": "Шаг два", "status": "pending"}]}}),
                         result()])
        self.assertEqual(self._of("tool"), [])
        steps = self._of("plan")[0]["steps"]
        self.assertEqual([s["title"] for s in steps], ["Шаг один", "Шаг два"])
        self.assertEqual([s["completed"] for s in steps], [True, False])

    async def test_an_edit_reports_the_file_it_touched(self):
        await self._run([assistant({"type": "tool_use", "id": "toolu_e", "name": "Edit",
                                    "input": {"file_path": "app.py"}}), result()])
        card = self._of("tool")[0]
        self.assertEqual(card["kind"], "file_change")
        self.assertEqual(card["files"], [{"path": "app.py"}])

    async def test_a_failed_tool_result_is_shown_as_failed(self):
        await self._run([assistant({"type": "tool_use", "id": "toolu_x", "name": "Read",
                                    "input": {"file_path": "missing"}}),
                         user({"type": "tool_result", "tool_use_id": "toolu_x",
                               "is_error": True, "content": "no such file"}),
                         result()])
        card = self._of("tool")[-1]
        self.assertEqual((card["status"], card["exit_code"]), ("failed", 1))
        self.assertIn("no such file", card["output"])

    async def test_a_result_without_its_call_is_dropped(self):
        # Otherwise a card would be closed that was never opened.
        await self._run([user({"type": "tool_result", "tool_use_id": "toolu_ghost",
                               "content": "x"}), result()])
        self.assertEqual(self._of("tool"), [])

    async def test_thinking_blocks_are_not_shown(self):
        await self._run([assistant({"type": "thinking", "thinking": "внутренние рассуждения"}),
                         result()])
        self.assertEqual(self._of("message"), [])


class FailureTests(StreamHarness):
    async def test_an_error_with_exit_zero_and_subtype_success_still_fails(self):
        # Exactly what a lost login produced: the process succeeded, the turn did not.
        with self.assertRaises(RuntimeFailure) as caught:
            await self._run([result(is_error=True, terminal_reason="api_error",
                                    result="Not logged in · Please run /login")])
        self.assertIn("Not logged in", str(caught.exception))

    async def test_a_missing_result_event_is_a_failure(self):
        with self.assertRaises(RuntimeFailure):
            await self._run([assistant({"type": "text", "text": "почти"})])

    async def test_a_stopped_turn_is_named_by_its_subtype(self):
        with self.assertRaises(RuntimeFailure) as caught:
            await self._run([result(is_error=True, subtype="error_max_turns", result="")])
        self.assertIn("лимит шагов", str(caught.exception))

    async def test_denied_tools_are_named_because_they_appear_nowhere_else(self):
        with self.assertRaises(RuntimeFailure) as caught:
            await self._run([result(is_error=True, subtype="error_during_execution", result="",
                                    permission_denials=[{"tool_name": "Write"}])])
        self.assertIn("Write", str(caught.exception))

    async def test_an_empty_answer_is_not_a_result(self):
        with self.assertRaises(RuntimeFailure) as caught:
            await self._run([result(result="   ")])
        self.assertIn("без ответа", str(caught.exception))

    async def test_unusable_usage_is_reported_as_unknown_not_as_zero(self):
        output = await self._run([result(usage={"input_tokens": True, "output_tokens": 5})])
        self.assertIsNone(output["usage"])


class ArgumentTests(StreamHarness):
    async def test_a_writing_turn_may_edit_but_still_has_no_shell(self):
        await self._run(HAPPY)
        self.assertIn("acceptEdits", self.argv)
        # Compare names, not substrings: "Write" occurs inside "TodoWrite".
        tools = set(self.argv[self.argv.index("--tools") + 1].split(","))
        self.assertIn("Write", tools)
        # Withholding Bash is what makes "no network, no installs" structural.
        self.assertFalse(tools & {"Bash", "WebFetch", "WebSearch", "Task"})

    async def test_a_reading_turn_cannot_edit_at_all(self):
        await self._run(HAPPY, readonly=True)
        self.assertIn("dontAsk", self.argv)
        tools = set(self.argv[self.argv.index("--tools") + 1].split(","))
        self.assertFalse(tools & {"Write", "Edit", "Bash"})
        self.assertEqual(tools, {"Read", "Glob", "Grep", "TodoWrite"})

    async def test_the_users_own_settings_are_ignored(self):
        # ~/.claude/settings.json may allow Bash and bypassPermissions.
        await self._run(HAPPY)
        self.assertIn("--restricted", self.argv)
        self.assertIn("--strict-mcp-config", self.argv)
        self.assertIn("--disable-slash-commands", self.argv)
        self.assertIn("mcp__*", self.argv)

    async def test_a_schema_is_passed_and_its_object_comes_back_as_text(self):
        schema = {"type": "object", "properties": {"kind": {"type": "string"}}, "required": ["kind"]}
        output = await self._run([result(structured_output={"kind": "plan"})], schema=schema)
        self.assertIn("--json-schema", self.argv)
        self.assertEqual(json.loads(self.argv[self.argv.index("--json-schema") + 1]), schema)
        self.assertEqual(json.loads(output["text"]), {"kind": "plan"})
        self.assertTrue((self.directory / "schema.json").is_file())

    async def test_without_structured_output_the_plain_result_is_used(self):
        output = await self._run([result(result='{"kind": "answer"}')],
                                 schema={"type": "object", "properties": {}})
        self.assertEqual(json.loads(output["text"]), {"kind": "answer"})


class BinaryDiscoveryTests(unittest.TestCase):
    def test_an_explicit_binary_wins(self):
        with tempfile.NamedTemporaryFile() as handle:
            with patch.dict(os.environ, {"CLAUDE_WORKER_BIN": handle.name}):
                self.assertEqual(claude_binary(), str(Path(handle.name).resolve()))

    def test_a_missing_binary_says_what_to_do(self):
        with patch.dict(os.environ, {"CLAUDE_WORKER_BIN": "/nonexistent/claude"}):
            with patch("jev_agent.runtime.shutil.which", return_value=None):
                with patch("jev_agent.runtime.Path.home", return_value=Path("/nonexistent")):
                    with self.assertRaises(RuntimeFailure) as caught:
                        claude_binary()
        self.assertIn("CLAUDE_WORKER_BIN", str(caught.exception))


class WorkerSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name) / "sessions"

    def test_the_choice_is_remembered_across_a_resume(self):
        session = Session.create(self.base)
        self.assertEqual(session.status()["worker"], "codex")
        session.use_worker("claude")
        self.assertIsInstance(session.runner, ClaudeRunner)
        restored = Session.load(session.directory)
        self.assertEqual(restored.status()["worker"], "claude")
        self.assertIsInstance(restored.runner, ClaudeRunner)

    def test_an_unknown_worker_is_refused(self):
        session = Session.create(self.base)
        with self.assertRaises(ValueError):
            session.use_worker("gemini")
        with self.assertRaises(ValueError):
            session.busy = True
            session.use_worker("claude")

    def test_a_corrupted_saved_worker_does_not_load(self):
        session = Session.create(self.base)
        session.metadata["worker"] = "whatever"
        session.save()
        with self.assertRaises(ValueError):
            Session.load(session.directory)


if __name__ == "__main__":
    unittest.main()


class WorkerCommandTests(unittest.IsolatedAsyncioTestCase):
    """The switch has to exist where the user is: inside the chat, not only at launch."""

    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.session = Session.create(Path(self.temporary.name) / "sessions")

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def test_the_command_switches_the_worker_and_says_so(self):
        from jev_agent.tui import JevApp
        app = JevApp(self.session, guided=False)
        async with app.run_test():
            app._configure("worker", "claude")
            await app.workers.wait_for_complete()
        self.assertEqual(self.session.status()["worker"], "claude")
        self.assertIsInstance(self.session.runner, ClaudeRunner)

    async def test_an_unknown_worker_is_refused_without_changing_anything(self):
        from jev_agent.tui import JevApp
        app = JevApp(self.session, guided=False)
        async with app.run_test():
            app._configure("worker", "gemini")
            await app.workers.wait_for_complete()
        self.assertEqual(self.session.status()["worker"], "codex")

    async def test_the_command_menu_offers_both_workers(self):
        # Capture what the palette is built from; opening the modal is Textual's
        # business, and mounting it adds nothing to what this checks.
        from jev_agent.tui import JevApp
        captured = []

        class Capture:
            def __init__(self, title, items, *rest, **kwargs):
                captured.extend(items)

        app = JevApp(self.session, guided=False)
        async with app.run_test():
            with patch("jev_agent.tui.PickerScreen", Capture), patch.object(app, "push_screen"):
                app.action_palette()
        values = {item["value"] for item in captured}
        self.assertIn("/worker claude", values)
        self.assertIn("/worker codex", values)
