"""Small, independent Textual views. None of these widgets can execute a tool."""
from __future__ import annotations

import json
import re
import shlex
from pathlib import PurePosixPath
from typing import Any, Dict, List

from rich.markdown import Markdown
from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Collapsible, Input, OptionList, Static, TabbedContent, TabPane, TextArea

PINK = "#f2a0cc"
AMBER = PINK  # Compatibility for the application chrome and older imports.
CREAM = "#ede7f0"
MUTED = "#aaa0b2"
GREEN = "#aad7b2"
RED = "#ffaaa7"


def plain(value: Any, limit: int = 14000) -> str:
    """Remove terminal controls; callers choose literal text or Markdown."""
    result = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    result = "".join(ch for ch in result if ch in "\n\t" or (ord(ch) >= 32 and not 127 <= ord(ch) <= 159))
    return result if len(result) <= limit else result[:limit] + "\n… full output in the session events.jsonl"


class PromptEditor(TextArea):
    BINDINGS = [Binding("enter", "submit", "Send", show=False, priority=True),
                Binding("ctrl+j,shift+enter", "newline", "New line", show=False, priority=True),
                # A terminal reports Command in more than one way: with the kitty
                # keyboard protocol Cmd+Backspace arrives as ``super+backspace``,
                # while other clients send it as a meta-modified Backspace or
                # Delete, and some forward no Command modifier at all. Bind every
                # spelling and keep Ctrl+U, which every terminal can produce.
                Binding("super+backspace,meta+backspace,super+delete,meta+delete,ctrl+u",
                        "delete_line", "Delete line", show=False, priority=True)]

    class Submitted(Message):
        def __init__(self, editor: "PromptEditor") -> None:
            super().__init__()
            self.editor = editor
            self.text = editor.text

        @property
        def control(self) -> "PromptEditor":
            return self.editor

    def action_submit(self) -> None:
        if not self.read_only:
            self.post_message(self.Submitted(self))

    def action_newline(self) -> None:
        if not self.read_only:
            self.replace("\n", *self.selection, maintain_selection_offset=False)

    def on_paste(self, event: events.Paste) -> None:
        # The base TextArea inserts the text. Prevent App forwarding it twice.
        event.stop()


def command_summary(command: str) -> str:
    """Shorten display-only shell wrappers without interpreting any shell code."""
    value = command
    for _ in range(2):
        try:
            parts = shlex.split(value)
        except ValueError:
            break
        if (len(parts) == 3 and PurePosixPath(parts[0]).name in ("sh", "bash", "zsh", "dash", "fish")
                and parts[1] in ("-c", "-lc", "-ic", "-lic")):
            value = parts[2]
        else:
            break
    # Only the leading executable is replaced; operators and quoting stay intact.
    match = re.match(r"^\s*('[^']*'|\"[^\"]*\"|\S+)", value)
    if match:
        try:
            executable = shlex.split(match.group(1))[0]
        except (ValueError, IndexError):
            executable = ""
        if executable.startswith("/") and re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", PurePosixPath(executable).name):
            value = "python" + value[match.end():]
    return " ".join(plain(value, 500).split())


class _ToolPreview(Static):
    def on_click(self, event: events.Click) -> None:
        if isinstance(self.parent, ToolCard):
            self.parent.collapsed = not self.parent.collapsed
            event.stop()


class ConversationCard(Vertical):
    """Prose uses Markdown, while user content and operational logs stay literal."""
    def __init__(self, role: str, content: str, color: str = CREAM,
                 markdown: bool = False, kind: str = "message") -> None:
        super().__init__(classes="conversation-card " + kind)
        self.role, self.content, self.color = role, content, color
        self.markdown = markdown

    def compose(self) -> ComposeResult:
        yield Static(Text(self.role, style="bold " + self.color), classes="message-role")
        body = Markdown(self.content, code_theme="dracula", hyperlinks=False) if self.markdown else Text(self.content, style=CREAM)
        yield Static(body, classes="message-body")


class ToolCard(Collapsible):
    """One card per actual call, updated in place as its lifecycle arrives."""
    DEFAULT_CSS = """
    ToolCard > .tool-preview { display: none; height: 1; color: #aaa0b2; padding: 0 1; }
    ToolCard.-collapsed > .tool-preview { display: block; }
    ToolCard > .tool-preview:hover { color: #f2a0cc; }
    """

    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = dict(data)
        self.output_view = Static(Text(""), classes="tool-output")
        self.preview_view = _ToolPreview(Text(""), classes="tool-preview")
        super().__init__(self.output_view, title="", collapsed=True,
                         collapsed_symbol="▸", expanded_symbol="▾", classes="tool-card")
        self.update_event(data)

    def compose(self) -> ComposeResult:
        yield from super().compose()
        yield self.preview_view

    def update_event(self, data: Dict[str, Any]) -> None:
        self.data.update(data)
        state = str(self.data.get("status") or self.data.get("lifecycle") or "")
        lifecycle = str(self.data.get("lifecycle", ""))
        code = self.data.get("exit_code")
        failed = state in ("failed", "error", "cancelled", "stopped") or (code is not None and code != 0)
        unknown = state == "unknown"
        done = lifecycle == "completed" or state in ("done", "completed", "complete", "finished", "success", "passed") or code is not None
        self.is_terminal = bool(done or failed or unknown)
        symbol = "?" if unknown else "×" if failed else "✓" if done else "●"
        command = plain(self.data.get("command") or "", 18000)
        kind = str(self.data.get("kind") or "tool")
        label = {"command_execution": "Terminal", "shell": "Terminal", "acceptance": "Check",
                 "file_change": "Files", "mcp_tool_call": "Tool", "web_search": "Search",
                 "provider_error": "Provider error", "read": "Read"}.get(kind, kind)
        files = self.data.get("files")
        if kind == "file_change" and isinstance(files, list):
            count = len(files)
            noun = "file" if count == 1 else "files"
            summary = "{} {}".format(count, noun)
            if len(files) == 1 and isinstance(files[0], dict):
                summary = plain(files[0].get("path") or "1 file", 500)
        else:
            summary = command_summary(command)
        title = symbol
        if code is not None:
            title += " exit {}".format(code)
        elif state in ("cancelled", "stopped"):
            title += " stopped"
        elif unknown:
            title += " status unknown"
        title += "  ·  " + label
        if summary:
            title += "  ·  " + summary[:76] + ("…" if len(summary) > 76 else "")
        self.title = escape(title)
        self.set_class(failed, "tool-failed")
        self.set_class(done and not failed and not unknown, "tool-done")
        output = Text(("Command\n" + command if command else "Event type: " + kind) + "\n", style="bold " + CREAM)
        if isinstance(files, list) and files:
            output.append("\n" + plain(files, 14000) + "\n", style=MUTED)
        if self.data.get("output"):
            raw_output = str(self.data["output"])
            output.append("\n" + plain(raw_output, 18000), style=MUTED)
            lines = raw_output.splitlines()
            first_line = next((line for line in lines if line.strip()), "")
            preview = "{} lines · {}".format(len(lines), " ".join(plain(first_line, 300).split()))
        else:
            note = "No matching completion event for this record." if unknown else "The command finished with no text output." if done else "Execution stopped." if failed else "Waiting for the actual process output…"
            output.append("\n" + note, style=MUTED)
            preview = "No text output · click to expand" if done and not unknown and not failed else "Click to expand the details" if failed or unknown else "Running · click to expand"
        self.preview_view.update(Text(preview[:130] + ("…" if len(preview) > 130 else ""), style=MUTED))
        self.output_view.update(output)


class PickerScreen(ModalScreen):
    """Searchable keyboard-first picker, shared by commands, sessions and files."""
    BINDINGS = [Binding("escape", "cancel", "Close", show=False),
                Binding("down", "next", "Down", show=False, priority=True),
                Binding("up", "previous", "Up", show=False, priority=True)]
    DEFAULT_CSS = """
    PickerScreen { align: center middle; background: #18151d 90%; }
    #picker-box { width: 86; max-width: 94%; height: 80%; max-height: 34;
        padding: 1 2; background: #221c29; border: round #86536f; }
    #picker-heading { height: 1; color: #f2a0cc; text-style: bold; }
    #picker-description { height: 2; color: #aaa0b2; }
    #picker-search { border: round #6d455f; background: #2c2434; margin-bottom: 1; height: 3; }
    #picker-search:focus { border: round #f2a0cc; }
    #picker-options { height: 1fr; border: none; background: #221c29; padding: 0; }
    #picker-options > .option-list--option { padding: 0 1; margin-bottom: 1; }
    #picker-options > .option-list--option-highlighted { background: #4a2d43; color: #ede7f0; }
    #picker-hint { height: 1; margin-top: 1; color: #aaa0b2; }
    """

    def __init__(self, title: str, choices: List[Dict[str, Any]], placeholder: str = "Search…") -> None:
        super().__init__()
        self.heading, self.choices, self.placeholder = title, choices, placeholder
        self.filtered = list(choices)

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Static(Text(self.heading), id="picker-heading")
            yield Static(Text("Start typing a name or pick a row below."), id="picker-description")
            yield Input(placeholder=self.placeholder, id="picker-search")
            yield OptionList(id="picker-options")
            yield Static("↑ ↓ select   Enter open   Escape close", id="picker-hint")

    def on_mount(self) -> None:
        self._filter("")
        self.query_one(Input).focus()

    def _filter(self, query: str) -> None:
        tokens = query.lower().split()
        self.filtered = [item for item in self.choices if all(
            token in (str(item.get("title", "")) + " " + str(item.get("description", "")) + " " + str(item.get("value", ""))).lower()
            for token in tokens)]
        options = self.query_one(OptionList)
        options.clear_options()
        for item in self.filtered:
            label = Text(plain(item["title"], 300), style="bold " + CREAM)
            if item.get("description"):
                label.append("\n" + plain(item["description"], 250), style=MUTED)
            options.add_option(label)
        options.highlighted = 0 if self.filtered else None
        self.query_one("#picker-hint", Static).update(
            "{} of {} · ↑ ↓ select   Enter open   Esc close".format(len(self.filtered), len(self.choices))
            if self.filtered else "Nothing found · change the query or Esc to close")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._select()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._select()

    def _select(self) -> None:
        index = self.query_one(OptionList).highlighted
        if index is not None and index < len(self.filtered):
            self.dismiss(self.filtered[index].get("value"))

    def action_next(self) -> None:
        self.query_one(OptionList).action_cursor_down()

    def action_previous(self) -> None:
        self.query_one(OptionList).action_cursor_up()

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen):
    BINDINGS = [Binding("escape,f1", "dismiss", "Close", show=False)]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; background: #18151d 90%; }
    #help-box { width: 80; max-width: 94%; height: auto; max-height: 90%;
        padding: 1 3; background: #221c29; border: round #86536f; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-box"):
            yield Static(Text("JEVIS / HARNESS\n", style="bold " + AMBER))
            yield Static(Text(
                "Write the task in plain words. Jev picks bounded decisions; the worker "
                "produces the answer and files; the harness verifies the actual result.\n\n"
                "Enter       send the whole text\n"
                "Ctrl+J      new line, or Shift+Enter if the terminal supports it\n"
                "Ctrl+D      also sends the whole text\n"
                "⌘⌫ / Ctrl+U delete the current line; Ctrl+U works in any terminal\n"
                "F1 / Ctrl+P command search\n"
                "F2          insert an example without running it\n"
                "F3          exact event log\n"
                "F4          expand the editor\n"
                "F6          Jev decisions, graph, checks and files\n"
                "Ctrl+S      save the real screen to SVG\n"
                "Ctrl+C      stop the run; when idle, quit\n\n"
                "A paste keeps every paragraph and sends nothing.\n"
                "Sessions, files and Jev details are on the chat buttons.\n\n"
                "/sessions   resume a saved session\n"
                "/files      open the created files and diff\n"
                "/export     save the conversation to Markdown\n"
                "/mode auto  the worker may change files\n"
                "/mode plan  read only and plan\n"
                "/jev assist apply Jev decisions\n"
                "/jev observe show decisions, do not apply\n"
                "/jev off    do not call Jev\n\n"
                "/status  /stop  /clear  /example  /help  /quit\n\n"
                "Modes and sessions switch only when idle.\n"
                "A tool card expands on click or Enter.\n"
                "A 'prepared' status is not independent acceptance.\n"
                "Escape returns to the conversation.", style=CREAM))


class ArtifactScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Close", show=False)]
    DEFAULT_CSS = """
    ArtifactScreen { align: center middle; background: #18151d 90%; }
    #artifact-box { width: 94%; height: 90%; padding: 1 2;
        background: #221c29; border: round #86536f; }
    #artifact-title { height: 2; color: #f2a0cc; }
    #artifact-notice { height: auto; max-height: 4; color: #aaa0b2; }
    #artifact-tabs { height: 1fr; }
    #artifact-tabs Tab { color: #aaa0b2; }
    #artifact-tabs Tab.-active { color: #f2a0cc; text-style: bold; }
    #artifact-tabs Underline > .underline--bar { color: #f2a0cc; background: #4a2d43; }
    #artifact-tabs TabPane { height: 1fr; padding: 1 0; }
    .artifact-scroll { height: 1fr; }
    .artifact-source { height: auto; }
    """

    def __init__(self, artifact: Dict[str, Any]) -> None:
        super().__init__()
        self.artifact = artifact

    def compose(self) -> ComposeResult:
        data = self.artifact
        with Vertical(id="artifact-box"):
            yield Static(Text(plain(data.get("path", "File")) + "  ·  Escape to close"), id="artifact-title")
            yield Static(Text(plain(data.get("notice", ""))), id="artifact-notice")
            with TabbedContent(id="artifact-tabs"):
                with TabPane("File", id="artifact-source-tab"):
                    with VerticalScroll(classes="artifact-scroll"):
                        text = plain(data.get("text", ""), 65536)
                        yield Static(Syntax(text, data.get("language") or "text", theme="dracula",
                                            background_color="#221c29", word_wrap=True, line_numbers=True), classes="artifact-source")
                with TabPane("Diff", id="artifact-diff-tab"):
                    with VerticalScroll(classes="artifact-scroll"):
                        diff = data.get("diff") or "No diff was saved for this record."
                        yield Static(Syntax(plain(diff, 65536), "diff", theme="dracula",
                                            background_color="#221c29", word_wrap=True), classes="artifact-source")
