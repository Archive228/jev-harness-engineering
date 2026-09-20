"""Headless terminal interaction checks. Fake calls occur only in this test file."""
import asyncio
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input, RichLog, Static

from jev_agent.tui import EXAMPLE_PROMPT, HelpScreen, JevApp, plain, status_label


class FakeSession:
    def __init__(self, root):
        self.id = "test-session"
        self.workspace = root / "workspace"
        self.directory = root / "session"
        self.directory.mkdir()
        self.workspace.mkdir()
        self.history = []
        self.busy = False
        self.cancelled = False
        self.calls = []
        self.recorded = []
        self.release = None

    def status(self):
        return {"id": self.id, "busy": self.busy, "turns": len(self.calls)}

    def events(self):
        return list(self.recorded)

    def cancel(self):
        self.cancelled = True
        if self.release:
            self.release.set()

    async def run_turn(self, prompt, emit):
        self.calls.append(prompt)
        self.busy = True
        payloads = [
            ("user", {"text": prompt}),
            ("phase", {"name": "inspect", "status": "running", "detail": "Reading repository"}),
            ("plan", {"steps": [{"id": "P1", "title": "Fix the parser"}]}),
            ("jev", {"purpose": "route", "model": "test-only", "elapsed_ms": 2,
                     "answers": {"route": {"type": "choice", "choice": "repair", "confidence": .8,
                                            "probabilities": {"repair": .85, "ask": .15}}}}),
            ("tool", {"kind": "shell", "command": "python -m unittest", "status": "done",
                      "output": "[red]literal output[/red]", "exit_code": 0}),
            ("checks", {"items": [{"id": "C1", "title": "Parser handles timestamps", "passed": True}],
                        "passed": 1, "total": 1, "snapshot": "test-snapshot"}),
            ("files", {"changed": ["parser.py"]}),
            ("meters", {"jev_calls": 1, "worker_calls": 1, "checks": 1, "jev_tokens": 50}),
        ]
        for kind, data in payloads:
            event = {"seq": len(self.recorded) + 1, "type": kind, "elapsed_ms": 2, "data": data}
            self.recorded.append(event)
            emit(event)
            await asyncio.sleep(0)
        if self.release:
            await self.release.wait()
        outcome = "cancelled" if self.cancelled else "complete"
        event = {"seq": len(self.recorded) + 1, "type": "end", "elapsed_ms": 3,
                 "data": {"status": outcome, "summary": "Test-only result",
                          "acceptance_scope": "Только сохранённый контракт"}}
        self.recorded.append(event)
        emit(event)
        self.busy = False
        return {"status": outcome}


class TerminalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.session = FakeSession(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    async def test_manual_submit_real_event_view_and_followup(self):
        app = JevApp(self.session)
        async with app.run_test(size=(140, 45)) as pilot:
            self.assertEqual(self.session.calls, [])
            box = app.query_one("#prompt", Input)
            box.value = "Fix the parser"
            await pilot.press("enter")
            await pilot.pause(.15)
            self.assertEqual(self.session.calls, ["Fix the parser"])
            self.assertEqual(app._outcome, "complete")
            self.assertFalse(app._busy)
            self.assertEqual(app._meters["checks"], 1)
            self.assertIn("route", app.query_one("#decisions", Static).renderable.plain)
            self.assertIn("85.0%", app.query_one("#decisions", Static).renderable.plain)
            self.assertIn("Parser handles timestamps", app.query_one("#evidence", Static).renderable.plain)
            self.assertIn("Только сохранённый контракт", app.query_one("#evidence", Static).renderable.plain)
            self.assertIn("inspect", app.query_one("#graph", Static).renderable.plain)
            box.value = "Now add a regression test"
            await pilot.press("enter")
            await pilot.pause(.1)
            self.assertEqual(len(self.session.calls), 2)

    async def test_initial_prompt_and_example_never_run_automatically(self):
        app = JevApp(self.session, initial_prompt="Do not execute this until Enter")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            self.assertEqual(self.session.calls, [])
            self.assertEqual(app.query_one("#prompt", Input).value, "Do not execute this until Enter")
            await pilot.press("f2")
            self.assertEqual(app.query_one("#prompt", Input).value, EXAMPLE_PROMPT)
            self.session.example_prompt = "Задача из выбранного проекта"
            await pilot.press("f2")
            self.assertEqual(app.query_one("#prompt", Input).value, self.session.example_prompt)
            self.assertEqual(self.session.calls, [])

    async def test_event_toggle_menu_and_svg(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("f3")
            self.assertTrue(app.query_one("#event-log", RichLog).display)
            self.assertFalse(app.query_one("#chat", RichLog).display)
            await pilot.press("f1")
            self.assertIsInstance(app.screen, HelpScreen)
            await pilot.pause(.4)
            await pilot.press("escape")
            await pilot.press("ctrl+s")
            screenshots = list((self.session.directory / "screenshots").glob("*.svg"))
            self.assertEqual(len(screenshots), 1)
            self.assertIn("<svg", screenshots[0].read_text())

    async def test_80_by_24_keeps_prompt_on_screen(self):
        app = JevApp(self.session)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            prompt = app.query_one("#prompt", Input)
            self.assertFalse(app.query_one("#rail").display)
            self.assertGreater(prompt.region.width, 60)
            self.assertGreaterEqual(prompt.region.y, 0)
            self.assertLessEqual(prompt.region.bottom, 24)
            self.assertGreater(app.query_one("#chat").region.height, 2)

    async def test_stop_and_busy_input_preserve_followup(self):
        self.session.release = asyncio.Event()
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", Input)
            prompt.value = "Long task"
            await pilot.press("enter")
            await pilot.pause(.1)
            prompt.value = "Keep this follow-up"
            await pilot.press("enter")
            self.assertEqual(prompt.value, "Keep this follow-up")
            self.assertEqual(len(self.session.calls), 1)
            await pilot.press("ctrl+c")
            await pilot.pause(.1)
            self.assertTrue(self.session.cancelled)
            self.assertEqual(app._outcome, "cancelled")
            self.assertFalse(app._busy)

    async def test_replay_is_read_only_and_duplicate_events_not_counted(self):
        event = {"seq": 1, "type": "message", "elapsed_ms": 3,
                 "data": {"role": "worker", "text": "[bold]literal[/bold]"}}
        app = JevApp(self.session, replay_events=[event, event], initial_prompt="Never run")
        async with app.run_test(size=(120, 40)) as pilot:
            self.assertEqual(app._event_count, 1)
            app.query_one("#prompt", Input).value = "Do work"
            await pilot.press("enter")
            self.assertEqual(self.session.calls, [])
            app.query_one("#prompt", Input).value = "/status"
            await pilot.press("enter")
            self.assertEqual(self.session.calls, [])

    async def test_clear_only_clears_view_and_unknown_command_not_sent(self):
        event = {"seq": 1, "type": "message", "elapsed_ms": 3, "data": {"text": "Keep on disk"}}
        self.session.recorded = [event]
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", Input)
            prompt.value = "/clear"
            await pilot.press("enter")
            self.assertEqual(self.session.events(), [event])
            prompt.value = "/oops"
            await pilot.press("enter")
            self.assertEqual(self.session.calls, [])

    async def test_restored_turn_resets_elapsed_and_meters(self):
        self.session.recorded = [
            {"seq": 1, "type": "user", "elapsed_ms": 0, "data": {"text": "First task"}},
            {"seq": 2, "type": "end", "elapsed_ms": 301000,
             "data": {"status": "error", "meters": {"worker_calls": 2, "usage_complete": False}}},
            {"seq": 3, "type": "user", "elapsed_ms": 0, "data": {"text": "Continue"}},
            {"seq": 4, "type": "end", "elapsed_ms": 72000,
             "data": {"status": "ready", "meters": {"worker_calls": 1, "usage_complete": True}}},
        ]
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)):
            self.assertEqual(app._elapsed_ms, 72000)
            self.assertEqual(app._meters, {"worker_calls": 1, "usage_complete": True})
            status = app.query_one("#status", Static).renderable.plain
            self.assertIn("72.0s", status)
            self.assertNotIn("301.0s", status)
            self.assertNotIn("usage неполный", status)

    async def test_end_meters_mark_incomplete_usage_without_standalone_event(self):
        self.session.recorded = [{
            "seq": 1, "type": "end", "elapsed_ms": 300000,
            "data": {"status": "error", "reason": "worker_timeout",
                     "meters": {"jev_calls": 2, "worker_calls": 1, "checks": 0,
                                "jev_tokens": 125, "worker_tokens": 0, "usage_complete": False}},
        }]
        app = JevApp(self.session)
        async with app.run_test(size=(80, 24)):
            self.assertEqual(app._meters["jev_calls"], 2)
            self.assertEqual(app._meters["worker_calls"], 1)
            self.assertFalse(app._meters["usage_complete"])
            status = app.query_one("#status", Static).renderable.plain
            self.assertIn("usage неполный", status)
            self.assertLess(status.index("usage неполный"), 30)
            self.assertIn("Jev 2", status)

    async def test_graph_shows_all_seven_observed_phases(self):
        self.session.recorded = [
            {"seq": i + 1, "type": "phase", "elapsed_ms": i,
             "data": {"name": "observed-phase-{}".format(i), "status": "done"}}
            for i in range(7)
        ]
        app = JevApp(self.session)
        async with app.run_test(size=(140, 45)):
            graph = app.query_one("#graph", Static).renderable.plain
            for i in range(7):
                self.assertIn("observed-phase-{}".format(i), graph)
            self.assertEqual(len(graph.strip().splitlines()), 7)
            self.assertIn("└─▶", graph)

    async def test_closing_active_app_stops_process_and_clock(self):
        self.session.release = asyncio.Event()
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#prompt", Input).value = "Pending task"
            await pilot.press("enter")
            await pilot.pause(.3)
            self.assertTrue(app._busy)
            self.assertIsNotNone(app._clock)
        self.assertTrue(self.session.cancelled)
        self.assertIsNone(app._clock)
        # Already queued status callbacks cannot access removed screen children.
        app._refresh_status()
        app._refresh_all()

    def test_outcome_labels_distinguish_prepared_and_contract_checked(self):
        self.assertEqual(status_label("ready"), "Результат подготовлен")
        self.assertEqual(status_label("accepted"), "Проверки контракта пройдены")
        self.assertEqual(status_label("idle"), "Жду задачу")

    def test_external_text_is_literal_and_control_bytes_removed(self):
        self.assertEqual(plain("[red]x[/red]"), "[red]x[/red]")
        self.assertEqual(plain("\x1b[2Jhello\r\x00"), "[2Jhello")
        self.assertIn("полный вывод", plain("x" * 200, limit=20))
