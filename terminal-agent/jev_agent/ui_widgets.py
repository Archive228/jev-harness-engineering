"""Small, independent Textual views. None of these widgets can execute a tool."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from rich.markdown import Markdown
from rich.markup import escape
from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Collapsible, Input, OptionList, Static, TabbedContent, TabPane, TextArea

AMBER = "#d8ad73"
CREAM = "#e8e4da"
MUTED = "#999b94"
GREEN = "#a7b995"
RED = "#d99383"


def plain(value: Any, limit: int = 14000) -> str:
    """Remove terminal controls; callers choose literal text or Markdown."""
    result = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    result = "".join(ch for ch in result if ch in "\n\t" or (ord(ch) >= 32 and not 127 <= ord(ch) <= 159))
    return result if len(result) <= limit else result[:limit] + "\n… полный вывод в events.jsonl сессии"


class PromptEditor(TextArea):
    def on_paste(self, event: events.Paste) -> None:
        # The base TextArea inserts the text. Prevent App forwarding it twice.
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
        body = Markdown(self.content, code_theme="monokai", hyperlinks=False) if self.markdown else Text(self.content, style=CREAM)
        yield Static(body, classes="message-body")


class ToolCard(Collapsible):
    """One card per actual call, updated in place as its lifecycle arrives."""
    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = dict(data)
        self.output_view = Static(Text(""), classes="tool-output")
        super().__init__(self.output_view, title="", collapsed=True,
                         collapsed_symbol="▸", expanded_symbol="▾", classes="tool-card")
        self.update_event(data)

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
        command = plain(self.data.get("command") or self.data.get("kind") or "tool", 500)
        command_first = " ".join(command.split())
        title = "{}  {}".format(symbol, command_first[:105] + ("…" if len(command_first) > 105 else ""))
        if code is not None:
            title += "  ·  exit {}".format(code)
        elif state in ("cancelled", "stopped"):
            title += "  ·  остановлено"
        elif unknown:
            title += "  ·  статус неизвестен"
        self.title = escape(title)
        self.set_class(failed, "tool-failed")
        self.set_class(done and not failed and not unknown, "tool-done")
        output = Text(command + "\n", style="bold " + CREAM)
        if self.data.get("output"):
            output.append("\n" + plain(self.data["output"], 18000), style=MUTED)
        else:
            note = "В этой записи нет сопоставленного события завершения." if unknown else "Команда завершилась без текстового вывода." if done else "Выполнение остановлено." if failed else "Ожидаю фактический вывод процесса…"
            output.append("\n" + note, style=MUTED)
        self.output_view.update(output)


class PickerScreen(ModalScreen):
    """Searchable keyboard-first picker, shared by commands, sessions and files."""
    BINDINGS = [Binding("escape", "cancel", "Закрыть", show=False),
                Binding("down", "next", "Вниз", show=False, priority=True),
                Binding("up", "previous", "Вверх", show=False, priority=True)]
    DEFAULT_CSS = """
    PickerScreen { align: center middle; background: #101210 85%; }
    #picker-box { width: 86; max-width: 94%; height: 80%; max-height: 34;
        padding: 1 2; background: #222520; border: round #555b50; }
    #picker-heading { height: 2; color: #d8ad73; text-style: bold; }
    #picker-search { border: none; background: #2b2e28; margin-bottom: 1; height: 3; }
    #picker-options { height: 1fr; border: none; background: #222520; padding: 0; }
    #picker-options > .option-list--option-highlighted { background: #393f32; color: #e8e4da; }
    #picker-hint { height: 1; margin-top: 1; color: #999b94; }
    """

    def __init__(self, title: str, choices: List[Dict[str, Any]], placeholder: str = "Поиск…") -> None:
        super().__init__()
        self.heading, self.choices, self.placeholder = title, choices, placeholder
        self.filtered = list(choices)

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Static(Text(self.heading), id="picker-heading")
            yield Input(placeholder=self.placeholder, id="picker-search")
            yield OptionList(id="picker-options")
            yield Static("↑ ↓ выбрать   Enter открыть   Escape закрыть", id="picker-hint")

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
            label = Text(plain(item["title"], 300), style=CREAM)
            if item.get("description"):
                label.append("\n" + plain(item["description"], 250), style=MUTED)
            options.add_option(label)
        options.highlighted = 0 if self.filtered else None
        self.query_one("#picker-hint", Static).update(
            "↑ ↓ выбрать   Enter открыть   Escape закрыть" if self.filtered else "Ничего не найдено · Escape закрыть")

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
    BINDINGS = [Binding("escape,f1", "dismiss", "Закрыть", show=False)]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; background: #101210 85%; }
    #help-box { width: 80; max-width: 94%; height: auto; max-height: 90%;
        padding: 1 3; background: #222520; border: round #555b50; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-box"):
            yield Static(Text("JEV / HARNESS\n", style="bold " + AMBER))
            yield Static(Text(
                "Пишите обычную задачу. Jev выбирает ограниченные решения; исполнитель "
                "создаёт ответ и файлы; harness проверяет фактический результат.\n\n"
                "Enter       новая строка, вставка сохраняет все абзацы\n"
                "Ctrl+D      отправить весь текст\n"
                "F1 / Ctrl+P поиск команд\n"
                "F2          вставить пример без запуска\n"
                "F3          точный журнал событий\n"
                "F4          развернуть редактор\n"
                "F6          решения Jev, граф, проверки и файлы\n"
                "Ctrl+S      сохранить реальный экран в SVG\n"
                "Ctrl+C      остановить работу; в ожидании — выйти\n\n"
                "/sessions   продолжить сохранённую сессию\n"
                "/files      открыть созданные файлы и diff\n"
                "/export     сохранить разговор в Markdown\n"
                "/mode auto  исполнитель может менять файлы\n"
                "/mode plan  только чтение и план\n"
                "/jev assist применять решения Jev\n"
                "/jev observe показывать решения, не применять\n"
                "/jev off    не вызывать Jev\n\n"
                "/status  /stop  /clear  /example  /help  /quit\n\n"
                "Режимы и сессии переключаются только в ожидании.\n"
                "Карточка инструмента раскрывается по клику или Enter.\n"
                "Статус «подготовлено» не означает независимую приёмку.\n"
                "Escape — вернуться к разговору.", style=CREAM))


class ArtifactScreen(ModalScreen):
    BINDINGS = [Binding("escape", "dismiss", "Закрыть", show=False)]
    DEFAULT_CSS = """
    ArtifactScreen { align: center middle; background: #101210 90%; }
    #artifact-box { width: 94%; height: 90%; padding: 1 2;
        background: #1d201c; border: round #555b50; }
    #artifact-title { height: 2; color: #d8ad73; }
    #artifact-notice { height: auto; max-height: 4; color: #999b94; }
    #artifact-tabs { height: 1fr; }
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
            yield Static(Text(plain(data.get("path", "Файл")) + "  ·  Escape закрыть"), id="artifact-title")
            yield Static(Text(plain(data.get("notice", ""))), id="artifact-notice")
            with TabbedContent(id="artifact-tabs"):
                with TabPane("Файл", id="artifact-source-tab"):
                    with VerticalScroll(classes="artifact-scroll"):
                        text = plain(data.get("text", ""), 65536)
                        yield Static(Syntax(text, data.get("language") or "text", theme="monokai",
                                            background_color="#1d201c", word_wrap=True, line_numbers=True), classes="artifact-source")
                with TabPane("Diff", id="artifact-diff-tab"):
                    with VerticalScroll(classes="artifact-scroll"):
                        diff = data.get("diff") or "Для этой записи diff не сохранён."
                        yield Static(Syntax(plain(diff, 65536), "diff", theme="monokai",
                                            background_color="#1d201c", word_wrap=True), classes="artifact-source")
