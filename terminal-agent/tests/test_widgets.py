"""Interaction checks for the terminal's reusable controls; no model calls."""
from pathlib import Path
import unittest

from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList, Static

from jev_agent.ui_widgets import PickerScreen, PromptEditor, ToolCard


class WidgetApp(App):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.submitted = []

    def compose(self) -> ComposeResult:
        yield self.widget

    def on_prompt_editor_submitted(self, event):
        self.submitted.append(event.text)


class ToolCardTests(unittest.IsolatedAsyncioTestCase):
    async def test_shell_title_is_readable_and_full_command_remains_literal(self):
        command = '/bin/zsh -lc "/tmp/project/.venv/bin/python -m unittest -v"'
        card = ToolCard({"kind": "command_execution", "command": command,
                         "status": "completed", "exit_code": 0,
                         "output": "[red]literal[/red]\nsecond line\n"})
        async with WidgetApp(card).run_test(size=(110, 25)):
            self.assertIn("Terminal", card.title)
            self.assertIn("python -m unittest -v", card.title)
            self.assertNotIn("zsh", card.title)
            self.assertIn(command, card.output_view.renderable.plain)
            self.assertIn("[red]literal[/red]", card.output_view.renderable.plain)
            self.assertIn("2 lines", card.preview_view.renderable.plain)
            self.assertTrue(card.collapsed)

    async def test_collapsed_preview_opens_and_hidden_when_expanded(self):
        card = ToolCard({"kind": "shell", "command": "pwd", "exit_code": 0,
                         "output": "/tmp/workspace\n"})
        async with WidgetApp(card).run_test(size=(110, 25)) as pilot:
            self.assertTrue(card.preview_view.display)
            await pilot.click(".tool-preview")
            await pilot.pause()
            self.assertFalse(card.collapsed)
            self.assertFalse(card.preview_view.display)
            self.assertTrue(card.output_view.display)

    async def test_long_output_counts_all_lines_but_bounds_rendered_detail(self):
        card = ToolCard({"kind": "acceptance", "command": "python -m unittest",
                         "output": ("test_record ... ok\n" * 2000), "exit_code": 7})
        async with WidgetApp(card).run_test(size=(100, 25)):
            self.assertTrue(card.title.startswith("× exit 7"))
            self.assertIn("Check", card.title)
            self.assertIn("2000 lines", card.preview_view.renderable.plain)
            self.assertIn("full output in the session events.jsonl", card.output_view.renderable.plain)
            self.assertLess(len(card.output_view.renderable.plain), 18500)
            self.assertTrue(card.has_class("tool-failed"))

    async def test_file_event_shows_real_file_count_and_details(self):
        files = [{"path": "src/main.py", "kind": "update"},
                 {"path": "tests/test_main.py", "kind": "add"}]
        card = ToolCard({"kind": "file_change", "files": files, "status": "completed"})
        async with WidgetApp(card).run_test(size=(110, 25)):
            self.assertIn("Files", card.title)
            self.assertIn("2 files", card.title)
            self.assertIn("src/main.py", card.output_view.renderable.plain)
            self.assertIn("tests/test_main.py", card.output_view.renderable.plain)
            self.assertNotIn("Command\n", card.output_view.renderable.plain)

    async def test_running_update_does_not_invent_exit_and_later_keeps_literal_command(self):
        command = "/bin/zsh -lc 'echo $(untrusted) && printf \"[green]\"'"
        card = ToolCard({"kind": "command_execution", "command": command, "status": "running"})
        async with WidgetApp(card).run_test(size=(110, 25)):
            self.assertFalse(card.is_terminal)
            self.assertNotIn("exit", card.title)
            self.assertIn("$(untrusted)", card.title)
            self.assertIn(command, card.output_view.renderable.plain)
            card.update_event({"status": "unknown"})
            self.assertTrue(card.is_terminal)
            self.assertIn("status unknown", card.title)
            self.assertFalse(card.has_class("tool-done"))
            self.assertIn(command, card.output_view.renderable.plain)


class EditorTests(unittest.IsolatedAsyncioTestCase):
    async def test_paste_is_complete_and_only_enter_sends(self):
        editor = PromptEditor()
        app = WidgetApp(editor)
        text = "Первая строка\n\nВторая строка\npython -m unittest"
        async with app.run_test(size=(100, 25)) as pilot:
            editor.focus()
            editor.post_message(events.Paste(text))
            await pilot.pause()
            self.assertEqual(editor.text, text)
            self.assertEqual(app.submitted, [])
            await pilot.press("enter")
            self.assertEqual(app.submitted, [text])
            self.assertEqual(editor.text, text)

    async def test_newline_shortcuts_preserve_multiline_composition(self):
        editor = PromptEditor()
        app = WidgetApp(editor)
        async with app.run_test(size=(100, 25)) as pilot:
            editor.focus()
            await pilot.press("a", "ctrl+j", "b", "shift+enter", "c")
            self.assertEqual(editor.text, "a\nb\nc")
            self.assertEqual(app.submitted, [])
            await pilot.press("enter")
            self.assertEqual(app.submitted, ["a\nb\nc"])

    async def test_modal_enter_selects_option_without_sending_editor(self):
        editor = PromptEditor("draft stays here")
        app = WidgetApp(editor)
        picked = []
        async with app.run_test(size=(100, 35)) as pilot:
            app.push_screen(PickerScreen("Sessions", [{"title": "Крипто", "description": "Сохранённый анализ", "value": "crypto"}]), picked.append)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(picked, ["crypto"])
            self.assertEqual(app.submitted, [])
            self.assertEqual(editor.text, "draft stays here")


class PickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_explains_count_and_preserves_selection_value(self):
        app = WidgetApp(Static("chat"))
        choices = [{"title": "Crypto Ledger", "description": "CSV и суммы", "value": "crypto"},
                   {"title": "Loglab", "description": "JSONL события", "value": "logs"}]
        picked = []
        async with app.run_test(size=(100, 35)) as pilot:
            app.push_screen(PickerScreen("Примеры", choices), picked.append)
            await pilot.pause()
            self.assertIn("2 of 2", str(app.screen.query_one("#picker-hint", Static).renderable))
            app.screen.query_one(Input).value = "csv"
            await pilot.pause()
            self.assertEqual(app.screen.query_one(OptionList).option_count, 1)
            self.assertIn("1 of 2", str(app.screen.query_one("#picker-hint", Static).renderable))
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(picked, ["crypto"])


class DeleteLineTests(unittest.IsolatedAsyncioTestCase):
    """Cmd+Backspace reaches an application under several different names."""

    def _binding(self):
        return next(b for b in PromptEditor.BINDINGS if b.action == "delete_line")

    def test_every_spelling_a_terminal_can_send_is_bound(self):
        keys = set(self._binding().key.split(","))
        # kitty keyboard protocol, meta-modified backspace and delete, and a
        # fallback every terminal can produce without a Command modifier.
        self.assertTrue({"super+backspace", "meta+backspace", "meta+delete", "ctrl+u"} <= keys)

    def test_the_binding_survives_modal_screens(self):
        self.assertTrue(self._binding().priority)

    async def test_it_removes_the_line_the_cursor_is_on(self):
        editor = PromptEditor(id="prompt")
        app = WidgetApp(editor)
        async with app.run_test():
            editor.load_text("первая\nвторая\nтретья")
            editor.cursor_location = (1, 3)
            editor.action_delete_line()
            await app.workers.wait_for_complete()
            self.assertEqual(editor.text, "первая\nтретья")

    async def test_the_on_screen_promise_names_a_key_that_is_actually_bound(self):
        from jev_agent import tui
        source = Path(tui.__file__).read_text(encoding="utf-8")
        keys = set(self._binding().key.split(","))
        self.assertIn("⌘⌫ or Ctrl+U", source)  # Promise the fallback too.
        self.assertIn("ctrl+u", keys)
