"""Headless terminal interaction checks. Fake calls occur only in this test file."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.markdown import Markdown
from textual import events
from textual.containers import VerticalScroll
from textual.widgets import Input, OptionList, RichLog, Static, TabbedContent, TextArea

from jev_agent.tui import EXAMPLE_PROMPT, HelpScreen, JevApp, plain, status_label
from jev_agent.ui_widgets import ArtifactScreen, ConversationCard, PickerScreen, ToolCard


CRYPTO_PROMPT = """Создай CLI «Crypto Detective» на Python без внешних библиотек.

Он принимает CSV транзакций с полями:
tx_hash, timestamp, from_address, to_address, token, amount.

Построй граф переводов между кошельками.
Найди цепочки до трёх переходов и круговые переводы.
Покажи конкретные tx_hash; отделяй наблюдения от гипотез.
Суммы считай через Decimal, разные токены не складывай.

Создай демонстрационные данные, запусти тесты и анализ.
Дай команду запуска для моего CSV."""


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
        self.execution_mode = "auto"
        self.jev_mode = "assist"

    def configure(self, **values):
        if self.busy:
            raise RuntimeError("busy")
        for name, value in values.items():
            if value not in {"execution_mode": ("auto", "plan"), "jev_mode": ("assist", "observe", "off")}[name]:
                raise ValueError("invalid mode")
            setattr(self, name, value)

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
            box = app.query_one("#prompt", TextArea)
            box.load_text("Fix the parser")
            await pilot.press("ctrl+d")
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
            box.load_text("Now add a regression test")
            await pilot.press("ctrl+d")
            await pilot.pause(.1)
            self.assertEqual(len(self.session.calls), 2)

    async def test_initial_prompt_and_example_never_run_automatically(self):
        app = JevApp(self.session, initial_prompt="Do not execute this until Ctrl+D")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            self.assertEqual(self.session.calls, [])
            self.assertEqual(app.query_one("#prompt", TextArea).text, "Do not execute this until Ctrl+D")
            await pilot.press("f2")
            self.assertEqual(app.query_one("#prompt", TextArea).text, EXAMPLE_PROMPT)
            self.session.example_prompt = "Задача из выбранного проекта"
            await pilot.press("f2")
            self.assertEqual(app.query_one("#prompt", TextArea).text, self.session.example_prompt)
            self.assertEqual(self.session.calls, [])

    async def test_multiline_paste_preserves_full_request_without_autosubmit(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            initial_height = prompt.region.height
            # Send the same event the terminal driver emits for bracketed paste.
            app.post_message(events.Paste(CRYPTO_PROMPT))
            await pilot.pause()
            self.assertEqual(prompt.text, CRYPTO_PROMPT)
            self.assertEqual(self.session.calls, [])
            self.assertTrue(prompt.soft_wrap)
            self.assertGreater(prompt.region.height, initial_height)
            await pilot.press("ctrl+d")
            await pilot.pause(.15)
            self.assertEqual(self.session.calls, [CRYPTO_PROMPT])
            self.assertEqual(prompt.text, "")
            self.assertEqual(
                [event["data"]["text"] for event in self.session.recorded
                 if event["type"] == "user"],
                [CRYPTO_PROMPT],
            )

    async def test_ctrl_j_inserts_newline_without_submitting(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            app.post_message(events.Paste("Первая строка"))
            await pilot.pause()
            await pilot.press("ctrl+j")
            app.post_message(events.Paste("Вторая строка"))
            await pilot.pause()
            self.assertEqual(prompt.text, "Первая строка\nВторая строка")
            self.assertEqual(self.session.calls, [])

    async def test_send_button_submits_entire_multiline_draft(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            prompt.load_text(CRYPTO_PROMPT)
            await pilot.pause()
            await pilot.click("#send-prompt")
            await pilot.pause(.15)
            self.assertEqual(self.session.calls, [CRYPTO_PROMPT])
            self.assertEqual(prompt.text, "")

    async def test_f4_expands_and_collapses_editor_without_losing_draft(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            prompt.load_text(CRYPTO_PROMPT)
            await pilot.pause()
            compact_height = prompt.region.height
            self.assertFalse(app._expanded_input)
            await pilot.press("f4")
            await pilot.pause()
            self.assertTrue(app._expanded_input)
            self.assertGreater(prompt.region.height, compact_height)
            self.assertEqual(prompt.text, CRYPTO_PROMPT)
            self.assertGreaterEqual(prompt.region.y, 0)
            self.assertLessEqual(prompt.region.bottom, 40)
            await pilot.press("f4")
            await pilot.pause()
            self.assertFalse(app._expanded_input)
            self.assertEqual(prompt.region.height, compact_height)
            self.assertEqual(prompt.text, CRYPTO_PROMPT)
            self.assertEqual(self.session.calls, [])

    async def test_80_by_24_long_draft_stays_accessible_and_inside_screen(self):
        app = JevApp(self.session)
        draft = "\n".join("Строка {}: {}".format(i, "проверь переводы " * 8)
                          for i in range(30))
        async with app.run_test(size=(80, 24)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            app.post_message(events.Paste(draft))
            await pilot.pause()
            self.assertEqual(prompt.text, draft)
            self.assertGreater(prompt.region.height, 3)
            self.assertGreaterEqual(prompt.region.y, 0)
            self.assertLessEqual(prompt.region.bottom, 24)
            self.assertEqual(prompt.cursor_location[0], 29)
            # A short terminal scrolls the document, never clips away the draft.
            self.assertGreater(prompt.scroll_y, 0)
            await pilot.press("f4")
            await pilot.pause()
            self.assertEqual(prompt.text, draft)
            self.assertLessEqual(prompt.region.bottom, 24)
            self.assertGreaterEqual(prompt.region.y, 0)
            self.assertEqual(self.session.calls, [])

    async def test_tab_moves_focus_without_inserting_into_draft(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            prompt.load_text("Сохрани этот текст")
            await pilot.press("tab")
            self.assertIsNot(app.focused, prompt)
            self.assertEqual(prompt.text, "Сохрани этот текст")
            self.assertEqual(self.session.calls, [])

    async def test_event_toggle_menu_and_svg(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("f3")
            self.assertTrue(app.query_one("#event-log", RichLog).display)
            self.assertTrue(app.query_one("#chat", VerticalScroll).display)
            self.assertEqual(app.query_one("#details-tabs", TabbedContent).active, "events-tab")
            await pilot.press("f1")
            self.assertIsInstance(app.screen, PickerScreen)
            await pilot.pause(.4)
            await pilot.press("escape")
            await pilot.press("ctrl+s")
            screenshots = list((self.session.directory / "screenshots").glob("*.svg"))
            self.assertEqual(len(screenshots), 1)
            self.assertIn("<svg", screenshots[0].read_text())

    async def test_wide_terminal_keeps_compact_live_logs_visible(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            rail = app.query_one("#rail")
            self.assertTrue(rail.display)
            self.assertEqual(app.query_one("#details-tabs", TabbedContent).active, "events-tab")
            self.assertIn("ЖИВЫЕ ЛОГИ", str(app.query_one("#drawer-title").renderable))
            self.assertTrue(app.query_one("#event-log", RichLog).display)

    async def test_command_delete_removes_current_line_and_keeps_other_lines(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            prompt.load_text("первая строка\nудалить эту строку\nтретья строка")
            prompt.move_cursor((1, 5))
            await pilot.press("meta+delete")
            await pilot.pause()
            self.assertEqual(prompt.text, "первая строка\nтретья строка")
            self.assertEqual(self.session.calls, [])

    async def test_80_by_24_keeps_prompt_on_screen(self):
        app = JevApp(self.session)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            prompt = app.query_one("#prompt", TextArea)
            self.assertFalse(app.query_one("#rail").display)
            self.assertGreater(prompt.region.width, 60)
            self.assertGreaterEqual(prompt.region.y, 0)
            self.assertLessEqual(prompt.region.bottom, 24)
            self.assertGreater(app.query_one("#chat").region.height, 2)

    async def test_stop_and_busy_input_preserve_followup(self):
        self.session.release = asyncio.Event()
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            prompt.load_text("Long task")
            await pilot.press("ctrl+d")
            await pilot.pause(.1)
            prompt.load_text("Keep this follow-up")
            await pilot.press("ctrl+d")
            self.assertEqual(prompt.text, "Keep this follow-up")
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
            app.query_one("#prompt", TextArea).load_text("Do work")
            await pilot.press("ctrl+d")
            self.assertEqual(self.session.calls, [])
            app.query_one("#prompt", TextArea).load_text("/status")
            await pilot.press("ctrl+d")
            self.assertEqual(self.session.calls, [])

    async def test_clear_only_clears_view_and_unknown_command_not_sent(self):
        event = {"seq": 1, "type": "message", "elapsed_ms": 3, "data": {"text": "Keep on disk"}}
        self.session.recorded = [event]
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            prompt.load_text("/clear")
            await pilot.press("ctrl+d")
            self.assertEqual(self.session.events(), [event])
            prompt.load_text("/oops")
            await pilot.press("ctrl+d")
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
            evidence = app.query_one("#evidence", Static).renderable.plain
            self.assertIn("Jev 2", evidence)
            self.assertIn("usage неполный", evidence)

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
            app.query_one("#prompt", TextArea).load_text("Pending task")
            await pilot.press("ctrl+d")
            await pilot.pause(.3)
            self.assertTrue(app._busy)
            self.assertIsNotNone(app._clock)
        self.assertTrue(self.session.cancelled)
        self.assertIsNone(app._clock)
        # Already queued status callbacks cannot access removed screen children.
        app._refresh_status()
        app._refresh_all()

    async def test_details_start_hidden_and_narrow_drawer_preserves_editor(self):
        app = JevApp(self.session)
        async with app.run_test(size=(80, 24)) as pilot:
            self.assertFalse(app.query_one("#rail").display)
            app.query_one("#prompt", TextArea).load_text("Не потерять черновик")
            await pilot.press("f6")
            await pilot.pause()
            self.assertTrue(app.query_one("#rail").display)
            self.assertFalse(app.query_one("#main").display)
            self.assertLessEqual(app.query_one("#prompt").region.bottom, 24)
            await pilot.press("f6")
            self.assertTrue(app.query_one("#main").display)
            self.assertEqual(app.query_one("#prompt", TextArea).text, "Не потерять черновик")

    async def test_tool_lifecycle_coalesces_and_does_not_merge_attempts(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            records = [
                {"call_id": "attempt-1", "item_id": "tool-1", "command": "python test.py", "status": "running"},
                {"call_id": "attempt-1", "item_id": "tool-1", "status": "done", "output": "[red]literal[/red]", "exit_code": 0},
                {"call_id": "attempt-2", "item_id": "tool-1", "command": "python test.py", "status": "running"},
            ]
            for i, data in enumerate(records):
                app.emit({"seq": i + 1, "type": "tool", "data": data})
            await pilot.pause()
            cards = list(app.query(ToolCard))
            self.assertEqual(len(cards), 2)
            first = cards[0]
            self.assertTrue(first.collapsed)
            self.assertEqual(first.data["exit_code"], 0)
            self.assertIn("[red]literal[/red]", first.output_view.renderable.plain)
            first.collapsed = False
            await pilot.pause()
            self.assertGreater(first.output_view.region.height, 0)
            self.assertEqual(app._event_count, 3)

    async def test_assistant_markdown_user_literal_and_no_duplicate_final(self):
        answer = "### Готово\n\nЗапусти `python run.py`."
        app = JevApp(self.session, replay_events=[
            {"seq": 1, "type": "user", "data": {"text": "[red]User[/red]"}},
            {"seq": 2, "type": "message", "data": {"role": "worker", "text": answer}},
            {"seq": 3, "type": "end", "data": {"status": "ready", "summary": answer, "reason": "registered_checks_passed"}},
        ])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            cards = list(app.query(ConversationCard))
            user = next(card for card in cards if card.role == "ВЫ")
            worker = next(card for card in cards if card.role == "АГЕНТ")
            self.assertEqual(user.content, "[red]User[/red]")
            self.assertFalse(user.markdown)
            self.assertIsInstance(worker.query_one(".message-body", Static).renderable, Markdown)
            self.assertEqual(sum(card.content == answer for card in cards), 1)

    async def test_palette_filters_and_changes_mode_without_sending_prompt(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+p")
            self.assertIsInstance(app.screen, PickerScreen)
            app.screen.query_one(Input).value = "режим план"
            await pilot.pause()
            self.assertEqual(app.screen.query_one(OptionList).option_count, 1)
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(self.session.execution_mode, "plan")
            self.assertEqual(self.session.calls, [])
            self.assertIs(app.screen, app._view)

    async def test_small_terminal_palette_scrolls_inside_dialog(self):
        app = JevApp(self.session)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f1")
            await pilot.pause()
            listing = app.screen.query_one(OptionList)
            hint = app.screen.query_one("#picker-hint")
            self.assertLessEqual(listing.region.bottom, hint.region.y)
            self.assertLessEqual(hint.region.bottom, 24)
            for _ in range(10):
                await pilot.press("down")
            self.assertEqual(listing.highlighted, 10)
            self.assertGreater(listing.scroll_y, 0)

    async def test_busy_session_cannot_change_mode_or_switch_session(self):
        self.session.release = asyncio.Event()
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app._submit("Long task")
            await pilot.pause(.1)
            app._submit("/mode plan")
            app._submit("/jev off")
            app._submit("/sessions")
            self.assertEqual(self.session.execution_mode, "auto")
            self.assertEqual(self.session.jev_mode, "assist")
            self.assertIs(app.screen, app._view)
            app._stop()
            await pilot.pause(.1)

    async def test_draft_persists_and_restores_without_submission(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#prompt", TextArea).load_text(CRYPTO_PROMPT)
            await pilot.pause(.4)
            self.assertEqual((self.session.directory / "draft.txt").read_text(), CRYPTO_PROMPT)
        resumed = JevApp(self.session)
        async with resumed.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            self.assertEqual(resumed.query_one("#prompt", TextArea).text, CRYPTO_PROMPT)
            self.assertEqual(self.session.calls, [])

    async def test_oversized_request_stays_in_editor_and_does_not_run(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            draft = "x" * 20001
            app.query_one("#prompt", TextArea).load_text(draft)
            await pilot.press("ctrl+d")
            self.assertEqual(app.query_one("#prompt", TextArea).text, draft)
            self.assertEqual(self.session.calls, [])

    async def test_immediate_exit_saves_draft_before_debounce(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#prompt", TextArea).load_text("Быстрый выход")
            app.action_stop_or_quit()
        self.assertEqual((self.session.directory / "draft.txt").read_text(), "Быстрый выход")

    async def test_artifact_picker_opens_file_and_diff_without_execution(self):
        (self.session.workspace / "answer.py").write_text("print('hello')\n")
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app._submit("/files")
            await pilot.pause()
            self.assertIsInstance(app.screen, PickerScreen)
            app.screen.query_one(Input).value = "answer.py"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertIsInstance(app.screen, ArtifactScreen)
            self.assertIn("print('hello')", app.screen.artifact["text"])
            self.assertEqual(self.session.calls, [])
            await pilot.press("escape")
            self.assertIs(app.screen, app._view)

    async def test_context_and_observe_decision_remain_visible_in_history(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app.emit({"seq": 1, "type": "context", "data": {"selection": "lexical", "selected": ["src/a.py"], "files_scanned": 3}})
            app.emit({"seq": 2, "type": "jev", "data": {"purpose": "route", "applied": False,
                      "answers": {"route": {"choice": "implement", "confidence": .9}}}})
            await pilot.pause()
            text = "\n".join(card.content for card in app.query(ConversationCard))
            self.assertIn("src/a.py", text)
            self.assertIn("решение не применяется", text)
            self.assertEqual(self.session.calls, [])

    async def test_context_decision_ids_resolve_to_real_file_lines_and_reset_next_turn(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            answer = {"purpose": "context", "applied": False, "answers": {"c0": {"type": "noul", "noul": .91}}}
            app.emit({"seq": 1, "type": "jev", "data": answer})
            await pilot.pause()
            self.assertIn("c0", app.query_one("#decisions", Static).renderable.plain)
            app.emit({"seq": 2, "type": "context", "data": {
                "selection": "lexical", "selected": ["README.md"], "files_scanned": 3,
                "candidates": [{"id": "c0", "path": "README.md", "start_line": 42, "end_line": 50}],
            }})
            await pilot.pause()
            view = app.query_one("#decisions", Static).renderable.plain
            self.assertIn("README.md:42–50 (c0)", view)
            self.assertIn("Noul 0.91", view)
            self.assertFalse(app._latest_jev["applied"])
            app.emit({"seq": 3, "type": "user", "data": {"text": "New task"}})
            app.emit({"seq": 4, "type": "jev", "data": answer})
            await pilot.pause()
            self.assertEqual(app._source_context, {})
            self.assertNotIn("README.md", app.query_one("#decisions", Static).renderable.plain)

    async def test_compact_phase_rail_marks_failures_and_cancellation(self):
        self.session.recorded = [
            {"seq": 1, "type": "phase", "data": {"name": "CODEX", "status": "error"}},
            {"seq": 2, "type": "phase", "data": {"name": "CHECKS", "status": "cancelled"}},
            {"seq": 3, "type": "phase", "data": {"name": "RESULT", "status": "stopped"}},
        ]
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)):
            ribbon = app.query_one("#phase-strip", Static).renderable.plain
            self.assertIn("× CODEX", ribbon)
            self.assertIn("× CHECKS", ribbon)
            self.assertIn("× RESULT", ribbon)
            self.assertNotIn("●", ribbon)

    async def test_restored_status_uses_same_saved_meters_as_header(self):
        self.session.recorded = [{"seq": 1, "type": "end", "elapsed_ms": 7000,
            "data": {"status": "ready", "meters": {"jev_calls": 3, "worker_calls": 2,
                     "jev_tokens": 210, "usage_complete": False}}}]
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app._submit("/status")
            await pilot.pause()
            card = next(item for item in app.query(ConversationCard) if item.role == "СЕССИЯ")
            report = json.loads(card.content)
            self.assertEqual(report["jev_calls"], 3)
            self.assertEqual(report["worker_calls"], 2)
            self.assertEqual(report["jev_tokens"], 210)
            self.assertFalse(report["usage_complete"])

    async def test_switch_session_restores_target_draft_and_resets_event_ids(self):
        replacement_dir = Path(self.temp.name) / "replacement"
        replacement_dir.mkdir()
        replacement = FakeSession(replacement_dir)
        replacement.id = "other-session"
        replacement.recorded = [{"seq": 1, "type": "message", "data": {"text": "Other session"}}]
        (replacement.directory / "draft.txt").write_text("Other draft")
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#prompt", TextArea).load_text("Old draft")
            app._receive({"seq": 1, "type": "message", "data": {"text": "Old session"}})
            with patch("jev_agent.core.Session.load", return_value=replacement):
                await app._session_selected(str(replacement.directory))
            await pilot.pause()
            self.assertIs(app.session, replacement)
            self.assertEqual(app._event_count, 1)
            self.assertEqual(app.query_one("#prompt", TextArea).text, "Other draft")
            self.assertEqual((self.session.directory / "draft.txt").read_text(), "Old draft")
            self.assertEqual(replacement.calls, [])

    async def test_tool_finished_lifecycle_and_interruption_are_truthful(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app.emit({"seq": 1, "type": "tool", "data": {"item_id": "read", "status": "finished", "lifecycle": "completed", "kind": "read"}})
            app.emit({"seq": 2, "type": "tool", "data": {"item_id": "run", "status": "running", "command": "slow task"}})
            app.emit({"seq": 3, "type": "end", "data": {"status": "cancelled"}})
            await pilot.pause()
            cards = list(app.query(ToolCard))
            self.assertTrue(cards[0].is_terminal)
            self.assertTrue(cards[0].has_class("tool-done"))
            self.assertTrue(cards[1].is_terminal)
            self.assertIn("остановлено", cards[1].title)
            self.assertFalse(cards[1].has_class("tool-done"))

    async def test_legacy_unmatched_tool_not_left_running_in_restored_history(self):
        self.session.recorded = [
            {"seq": 1, "type": "tool", "data": {"command": "legacy", "status": "running"}},
            {"seq": 2, "type": "end", "data": {"status": "ready"}},
        ]
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card = app.query_one(ToolCard)
            self.assertTrue(card.is_terminal)
            self.assertIn("статус неизвестен", card.title)
            self.assertNotIn("●", card.title)
            self.assertFalse(card.has_class("tool-done"))
            header = app.query_one("#masthead", Static).renderable.plain
            self.assertIn("Готов к сообщению", header)
            self.assertNotIn("LIVE", header)

    def test_outcome_labels_distinguish_prepared_and_contract_checked(self):
        self.assertEqual(status_label("ready"), "Результат подготовлен")
        self.assertEqual(status_label("accepted"), "Проверки контракта пройдены")
        self.assertEqual(status_label("idle"), "Жду задачу")

    def test_external_text_is_literal_and_control_bytes_removed(self):
        self.assertEqual(plain("[red]x[/red]"), "[red]x[/red]")
        self.assertEqual(plain("\x1b[2Jhello\r\x00"), "[2Jhello")
        self.assertIn("полный вывод", plain("x" * 200, limit=20))
