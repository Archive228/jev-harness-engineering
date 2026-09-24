"""User-flow regressions for the compact chat UI; no models or APIs are called."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual import events
from textual.containers import VerticalScroll
from textual.widgets import Button, TextArea

from jev_agent.activity import ActivityGroup
from jev_agent.catalog import load_draft, save_draft
from jev_agent.core import Session
from jev_agent.tui import JevApp
from jev_agent.ui_widgets import ConversationCard, PickerScreen, ToolCard
from test_tui import CRYPTO_PROMPT, FakeSession


class ConvenientChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.session = FakeSession(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def saved_turn(self, answer="Готово.\n\n```sh\npython ledger.py\n```", number=1):
        """A burst of saved events also exercises deferred child mounting."""
        payloads = [
            ("user", {"text": "Проверь баланс {}".format(number)}),
            ("tool", {"kind": "shell", "command": "python -m unittest",
                      "call_id": "turn-{}".format(number), "item_id": "one",
                      "lifecycle": "started"}),
            ("tool", {"kind": "shell", "command": "python -m unittest",
                      "call_id": "turn-{}".format(number), "item_id": "one",
                      "lifecycle": "completed", "exit_code": 0, "output": "OK"}),
            ("message", {"role": "worker", "text": answer}),
            ("checks", {"passed": 1, "total": 1,
                        "items": [{"id": "balance", "title": "Баланс", "passed": True}]}),
            ("jev", {"purpose": "review", "answers": {
                "next_action": {"choice": "finish", "confidence": .8}}}),
            ("files", {"changed": ["ledger.py"]}),
            ("end", {"status": "accepted", "summary": answer,
                     "acceptance_scope": "Проверен сохранённый контракт."}),
        ]
        for kind, data in payloads:
            self.session.recorded.append({"seq": len(self.session.recorded) + 1,
                                          "type": kind, "data": data, "elapsed_ms": 1})
        return answer

    async def test_paste_does_not_send_and_enter_sends_complete_multiline_once(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            app.post_message(events.Paste(CRYPTO_PROMPT))
            await pilot.pause()
            self.assertEqual(self.session.calls, [])
            self.assertEqual(app.query_one("#prompt", TextArea).text, CRYPTO_PROMPT)
            await pilot.press("enter", "enter")
            await pilot.pause(.15)
            self.assertEqual(self.session.calls, [CRYPTO_PROMPT])
            self.assertEqual(app.query_one("#prompt", TextArea).text, "")

    async def test_newline_shortcut_preserves_text_until_explicit_send(self):
        app = JevApp(self.session)
        async with app.run_test(size=(100, 32)) as pilot:
            app.post_message(events.Paste("Первая строка"))
            await pilot.pause()
            await pilot.press("ctrl+j")
            app.post_message(events.Paste("Вторая строка"))
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt", TextArea).text, "Первая строка\nВторая строка")
            self.assertEqual(self.session.calls, [])

    async def test_saved_burst_groups_tools_and_leaves_one_answer_outside_activity(self):
        answer = self.saved_turn()
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            groups = list(app.query(ActivityGroup))
            self.assertEqual(len(groups), 1)
            self.assertTrue(groups[0].collapsed)
            self.assertEqual(len(list(groups[0].query(ToolCard))), 1)
            answers = [card for card in app.query(ConversationCard) if card.content == answer]
            self.assertEqual(len(answers), 1)
            self.assertIs(answers[0].parent, app.query_one("#chat", VerticalScroll))
            self.assertTrue(answers[0].has_class("answer"))
            # Operational events must all precede the result in the chat.
            chat_children = list(app.query_one("#chat", VerticalScroll).children)
            self.assertLess(chat_children.index(groups[0]), chat_children.index(answers[0]))
            self.assertIs(chat_children[-1], answers[0])
            self.assertEqual(self.session.calls, [])

    async def test_ctrl_o_only_toggles_latest_turn_activity(self):
        self.saved_turn("Первый результат", 1)
        self.saved_turn("Последний результат", 2)
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            groups = list(app.query(ActivityGroup))
            self.assertEqual(len(groups), 2)
            await pilot.press("ctrl+o")
            self.assertTrue(groups[0].collapsed)
            self.assertFalse(groups[1].collapsed)
            await pilot.press("ctrl+o")
            self.assertTrue(groups[1].collapsed)

    async def test_restored_large_history_stays_at_latest_answer_after_mounting(self):
        for number in range(1, 9):
            self.saved_turn("Ответ {}\n\n".format(number) + "\n\n".join(
                "Параграф {}: {}".format(line, "Проверенный результат. " * 4)
                for line in range(14)), number)
        app = JevApp(self.session)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause(.4)
            chat = app.query_one("#chat", VerticalScroll)
            self.assertGreater(chat.max_scroll_y, chat.region.height)
            self.assertTrue(chat.is_vertical_scroll_end,
                            "Restored history left the newest answer below the viewport: "
                            "scroll_y={}, max_scroll_y={}, height={}".format(
                                chat.scroll_y, chat.max_scroll_y, chat.region.height))
            self.assertEqual(len(list(app.query(ActivityGroup))), 8)
            self.assertEqual(len(list(app.query(ToolCard))), 8)

    async def test_visible_navigation_opens_pickers_without_losing_draft(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            prompt = app.query_one("#prompt", TextArea)
            prompt.load_text(CRYPTO_PROMPT)
            for selector, heading in (("#nav-files", "Session files"),
                                      ("#nav-menu", "Commands"),
                                      ("#nav-sessions", "Sessions")):
                self.assertTrue(app.query_one(selector, Button).display)
                await pilot.click(selector)
                await pilot.pause()
                self.assertIsInstance(app.screen, PickerScreen)
                self.assertEqual(app.screen.heading, heading)
                await pilot.press("escape")
                await pilot.pause()
                self.assertEqual(prompt.text, CRYPTO_PROMPT)
            self.assertEqual(self.session.calls, [])

    async def test_guided_picker_explains_default_and_direct_bypass(self):
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#guided-picker")
            await pilot.pause()
            self.assertIsInstance(app.screen, PickerScreen)
            text = "\n".join(str(item) for item in app.screen.choices)
            self.assertIn("Discussion and plan", text)
            self.assertIn("Straight to the task", text)
            await pilot.press("escape")
            self.assertEqual(self.session.calls, [])

    async def test_new_chat_keeps_previous_draft_and_returns_to_blank_editor(self):
        first = Session.create(Path(self.temp.name) / "real-sessions")
        app = JevApp(first)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#prompt", TextArea).load_text(CRYPTO_PROMPT)
            await pilot.click("#nav-new")
            await pilot.pause(.2)
            self.assertNotEqual(app.session.id, first.id)
            self.assertEqual(load_draft(first), CRYPTO_PROMPT)
            self.assertEqual(app.query_one("#prompt", TextArea).text, "")
            self.assertNotEqual(app.session.workspace, first.workspace)
            self.assertEqual(app.session.events(), [])
            self.assertFalse(app._busy)

    async def test_pending_autosave_cannot_overwrite_destination_session_draft(self):
        base = Path(self.temp.name) / "real-sessions"
        first, second = Session.create(base), Session.create(base)
        save_draft(second, "Черновик второй сессии")
        app = JevApp(first)
        async with app.run_test(size=(100, 32)) as pilot:
            app.query_one("#prompt", TextArea).load_text("Новый черновик первой сессии")
            # Let TextArea.Changed schedule the real debounced autosave, but
            # switch before it fires. A long history can take time to unmount.
            await pilot.pause(.01)
            chat = app.query_one("#chat", VerticalScroll)
            original_remove = chat.remove_children

            async def slow_history_unmount(*args, **kwargs):
                await asyncio.sleep(.4)
                await original_remove(*args, **kwargs)

            with patch.object(chat, "remove_children", side_effect=slow_history_unmount):
                await app._session_selected(str(second.directory))
            await pilot.pause()
            self.assertEqual(load_draft(first), "Новый черновик первой сессии")
            self.assertEqual(load_draft(second), "Черновик второй сессии")
            self.assertEqual(app.query_one("#prompt", TextArea).text, "Черновик второй сессии")
            self.assertEqual(app.session.id, second.id)

    async def test_stop_button_stops_work_without_exiting_or_losing_followup(self):
        self.session.release = asyncio.Event()
        app = JevApp(self.session)
        async with app.run_test(size=(100, 32)) as pilot:
            app.query_one("#prompt", TextArea).load_text("Долгая задача")
            await pilot.press("enter")
            await pilot.pause(.1)
            self.assertTrue(app.query_one("#stop-run", Button).display)
            self.assertFalse(app.query_one("#send-prompt", Button).display)
            self.assertTrue(app.query_one("#nav-new", Button).disabled)
            app.query_one("#prompt", TextArea).load_text("Сохрани черновик")
            await pilot.click("#stop-run")
            await pilot.pause(.2)
            self.assertTrue(self.session.cancelled)
            self.assertFalse(app._busy)
            self.assertTrue(app.is_running)
            self.assertEqual(app.query_one("#prompt", TextArea).text, "Сохрани черновик")
            self.assertFalse(app.query_one("#stop-run", Button).display)
            self.assertTrue(app.query_one("#send-prompt", Button).display)

    async def test_copy_keeps_full_answer_and_export_writes_real_saved_events(self):
        answer = self.saved_turn("Начало\n" + "Очень длинный ответ. " * 900 + "\nПоследняя строка")
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            with patch.object(app, "copy_to_clipboard") as clipboard:
                await pilot.click("#result-copy")
                clipboard.assert_called_once_with(answer)
            fallback = self.session.directory / "exports" / "answer.txt"
            self.assertEqual(fallback.read_text(encoding="utf-8"), answer)
            await pilot.click("#result-export")
            await pilot.pause()
            export = self.session.directory / "exports" / "session.md"
            self.assertTrue(export.is_file())
            content = export.read_text(encoding="utf-8")
            self.assertIn("Последняя строка", content)
            self.assertIn("python -m unittest", content)
            self.assertIn('"status": "accepted"', content)
            self.assertEqual(self.session.calls, [])

    async def test_copy_answer_keeps_file_fallback_when_terminal_clipboard_fails(self):
        answer = self.saved_turn("Полный ответ\n" + "строка. " * 300)
        app = JevApp(self.session)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            with patch.object(app, "copy_to_clipboard", side_effect=RuntimeError("OSC52 disabled")):
                await pilot.click("#result-copy")
            fallback = self.session.directory / "exports" / "answer.txt"
            self.assertEqual(fallback.read_text(encoding="utf-8"), answer)

    async def test_short_terminal_keeps_result_buttons_and_editor_inside_view(self):
        self.saved_turn()
        app = JevApp(self.session)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            for selector in ("#result-answer", "#result-files", "#result-copy",
                             "#result-export", "#prompt", "#send-prompt"):
                widget = app.query_one(selector)
                self.assertTrue(widget.display, selector)
                self.assertGreater(widget.region.width, 0, selector)
                self.assertGreaterEqual(widget.region.x, 0, selector)
                self.assertLessEqual(widget.region.right, 80, selector)
                self.assertGreaterEqual(widget.region.y, 0, selector)
                self.assertLessEqual(widget.region.bottom, 24, selector)
            self.assertGreater(app.query_one("#chat").region.height, 0)

    async def test_large_paste_expansion_and_escape_preserve_full_editable_draft(self):
        draft = "\n".join("{}: {}".format(i, "проверь криптоперевод " * 6) for i in range(24))
        app = JevApp(self.session)
        async with app.run_test(size=(80, 24)) as pilot:
            app.post_message(events.Paste(draft))
            await pilot.pause()
            editor = app.query_one("#prompt", TextArea)
            compact_height = editor.region.height
            await pilot.click("#expand-prompt")
            await pilot.pause()
            self.assertTrue(app._expanded_input)
            self.assertGreater(editor.region.height, compact_height)
            self.assertLessEqual(editor.region.bottom, 24)
            self.assertEqual(editor.text, draft)
            await pilot.press("escape")
            await pilot.pause()
            self.assertFalse(app._expanded_input)
            self.assertEqual(editor.text, draft)
            self.assertEqual(self.session.calls, [])


if __name__ == "__main__":
    unittest.main()
