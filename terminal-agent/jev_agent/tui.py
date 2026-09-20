"""A terminal view of real harness events; rendering never runs tools itself."""
from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, RichLog, Static, TextArea

PINK = "#fb9ec9"
CREAM = "#f0eadf"
MUTED = "#9693aa"
GREEN = "#9fdfb7"
YELLOW = "#eed18c"
EXAMPLE_PROMPT = (
    "Создай CLI-анализатор инцидентов: читай JSONL, группируй ошибки по сервису и причине, "
    "убирай дубли event_id, правильно сравнивай часовые пояса и пропускай битые строки "
    "с предупреждением. Добавь пример данных, JSON- и Markdown-отчёт, тесты. "
    "Запусти тесты и покажи готовую команду запуска."
)


def plain(value: Any, limit: int = 14000) -> str:
    """Literal, bounded data; external output is never Rich markup."""
    if isinstance(value, str):
        result = value
    else:
        result = json.dumps(value, ensure_ascii=False, default=str)
    # Terminal controls must not become cursor movement or fake UI chrome.
    result = "".join(ch for ch in result if ch in "\n\t" or (ord(ch) >= 32 and not 127 <= ord(ch) <= 159))
    return result if len(result) <= limit else result[:limit] + "\n… полный вывод в events.jsonl сессии"


def number(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def status_label(status: str) -> str:
    return {
        "idle": "Жду задачу", "running": "Работает", "ready": "Результат подготовлен",
        "accepted": "Проверки контракта пройдены", "complete": "Ход завершён",
        "completed": "Ход завершён", "success": "Ход завершён", "ended": "Ход завершён",
        "cancelled": "Остановлено", "stopped": "Остановлено", "blocked": "Нужны данные",
        "error": "Ошибка", "failed": "Ошибка", "replay": "Запись",
        "needs_input": "Нужно уточнение", "answered": "Ответ подготовлен",
    }.get(status, status)


def reason_label(reason: str) -> str:
    return {
        "response_prepared_without_independent_acceptance": "Результат подготовлен; выполненные проверки — в панели справа.",
        "registered_checks_passed": "Все проверки сохранённого контракта пройдены.",
        "checks_failed_or_no_progress": "Есть упавшие проверки или исправления больше не дают прогресса.",
        "iteration_limit_or_no_progress": "Достигнут лимит попыток или нет новых изменений.",
        "review_requests_clarification": "Для продолжения Jev просит уточнить задачу.",
        "uncertain_request_correspondence": "Нужно уточнить, соответствует ли результат твоему запросу.",
        "user_cancelled": "Задача остановлена. Созданные файлы сохранены.",
    }.get(reason, reason)


class EventArrived(Message):
    """post_message also safely accepts events emitted from a worker thread."""

    def __init__(self, event: Dict[str, Any]) -> None:
        super().__init__()
        self.event = event


class PromptEditor(TextArea):
    """Multiline draft: pasted newlines are text, never submit events."""

    def on_paste(self, event: events.Paste) -> None:
        # TextArea still performs the insert; don't bubble the same paste back
        # to App, where an unforwarded event can be sent to the editor again.
        event.stop()


class HelpScreen(ModalScreen):
    BINDINGS = [Binding("escape,f1", "dismiss", "Закрыть", show=False)]
    DEFAULT_CSS = """
    HelpScreen { align: center middle; background: #070912 80%; }
    #help-box { width: 72; max-width: 94%; height: auto; max-height: 92%;
        padding: 1 3; background: #181a2b; border: round #fb9ec9; }
    #help-copy { height: auto; margin-bottom: 1; }
    #help-close { width: 100%; }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-box"):
            text = Text("JEV + HARNESS  /  агент в терминале\n\n", style=f"bold {PINK}")
            text.append(
                "Вставьте задачу целиком и нажмите Ctrl+D или кнопку «Отправить». "
                "Enter добавляет строку. Исполнитель читает и меняет файлы; "
                "Jev принимает структурированные решения в панели справа. "
                "Граф показывает только фактически выполненные этапы.\n\n",
                style=CREAM,
            )
            text.append("F2        Вставить пример задачи без запуска\n")
            text.append("F3        Переключить чат / журнал событий\n")
            text.append("F4        Развернуть / свернуть редактор сообщения\n")
            text.append("Ctrl+D    Отправить сообщение целиком\n")
            text.append("Ctrl+S    Сохранить текущий экран как SVG\n")
            text.append("Ctrl+C    Остановить задачу; в ожидании — выйти\n")
            text.append("Tab       Сменить фокус; PageUp / PageDown — листать\n\n")
            text.append("/help  /status  /stop  /clear  /example  /quit\n", style=GREEN)
            text.append(
                "\n/clear очищает только экран. События остаются на диске.\n"
                "Следующее сообщение продолжит работу в той же папке.\n"
                "Режим записи показывает сохранённые события без вызовов API.",
                style=MUTED,
            )
            yield Static(text, id="help-copy")
            yield Button("Вернуться к чату · Escape", id="help-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


class JevApp(App):
    """Live terminal conversation with an independently testable session."""

    TITLE = "Jev + Harness"
    SUB_TITLE = "Реальные решения · реальные инструменты · сохранённые доказательства"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+d", "submit_prompt", "Отправить", priority=True),
        Binding("ctrl+enter", "submit_prompt", "Отправить", priority=True, show=False),
        Binding("f1", "help", "Меню", priority=True),
        Binding("f2", "example", "Пример", priority=True),
        Binding("f3", "toggle_events", "Журнал", priority=True),
        Binding("f4", "expand_input", "Развернуть ввод", priority=True),
        Binding("ctrl+s", "save_view", "Снимок", priority=True),
        Binding("ctrl+c", "stop_or_quit", "Стоп / выход", priority=True),
    ]
    CSS = """
    Screen { background: #0c0e19; color: #f0eadf; }
    #masthead { height: 3; padding: 0 2; background: #181a2b; }
    #body { height: 1fr; padding: 0 1; }
    #main { width: 2fr; min-width: 30; }
    #graph-box { height: auto; max-height: 13; border: round #48415e;
        padding: 0 1; margin: 0 1 0 0; }
    #graph { height: auto; }
    #stream-box { height: 1fr; border: round #48415e; margin-right: 1; }
    .section-title { height: 1; color: #fb9ec9; padding: 0 1; text-style: bold; }
    #chat, #event-log { height: 1fr; padding: 0 1; scrollbar-size: 1 1; }
    #event-log { display: none; }
    #rail { width: 1fr; min-width: 30; max-width: 52; }
    #decisions-box { height: 1fr; border: round #48415e; padding: 0 1; }
    #evidence-box { height: 1fr; border: round #48415e; padding: 0 1; }
    #decisions-scroll, #evidence-scroll { height: 1fr; scrollbar-size: 1 1; }
    #decisions, #evidence { height: auto; }
    #status { height: 2; padding: 0 2; color: #9693aa; }
    #composer { height: auto; margin: 0 1; }
    #prompt { height: 5; border: round #fb9ec9; background: #181a2b; padding: 0 1; scrollbar-size: 1 1; }
    #prompt:focus { border: round #fb9ec9; }
    #composer-actions { height: 3; align-vertical: middle; }
    #prompt-meta { width: 1fr; height: 2; color: #9693aa; padding-left: 1; }
    #send-prompt { width: 23; min-width: 20; height: 3; background: #30263e; color: #fb9ec9; border: round #48415e; }
    Screen.input-expanded #body, Screen.input-expanded #status { display: none; }
    Screen.input-expanded #composer { height: 1fr; }
    #hint { height: 1; padding: 0 2; color: #9693aa; }
    Footer { background: #181a2b; color: #9693aa; }
    Footer > .footer--key { background: #30263e; color: #fb9ec9; }
    Screen.narrow #rail { display: none; }
    Screen.narrow #graph-box { max-height: 8; margin-right: 0; }
    Screen.narrow #stream-box { margin-right: 0; }
    Screen.short #masthead { height: 2; }
    Screen.short #graph-box { max-height: 6; }
    Screen.short #hint { display: none; }
    Screen.short #status { height: 1; }
    """

    def __init__(self, session: Any, initial_prompt: Optional[str] = None,
                 replay_events: Optional[list] = None) -> None:
        super().__init__()
        self.session = session
        self.initial_prompt = initial_prompt
        self.replay_events = replay_events
        self.is_replay = replay_events is not None
        self._busy = False
        self._event_count = 0
        self._event_types = []
        self._phases: Dict[str, Dict[str, Any]] = {}
        self._steps = []
        self._latest_jev: Dict[str, Any] = {}
        self._checks: Dict[str, Any] = {}
        self._acceptance_scope = ""
        self._files = []
        self._meters: Dict[str, Any] = {}
        self._outcome = "idle"
        self._detail = ""
        self._elapsed_ms = 0.0
        self._turn_started = None
        self._show_events = False
        self._expanded_input = False
        self._seen_sequences = set()
        self._runner = None
        self._view = None
        self._clock = None

    def compose(self) -> ComposeResult:
        yield Static(id="masthead")
        with Horizontal(id="body"):
            with Vertical(id="main"):
                with VerticalScroll(id="graph-box"):
                    yield Static("ГРАФ ВЫПОЛНЕНИЯ", classes="section-title")
                    yield Static(id="graph")
                with Vertical(id="stream-box"):
                    yield Static("ДИАЛОГ", id="stream-title", classes="section-title")
                    yield RichLog(id="chat", markup=False, highlight=False,
                                  wrap=True, min_width=20, max_lines=2500)
                    yield RichLog(id="event-log", markup=False, highlight=False,
                                  wrap=True, min_width=20, max_lines=4000)
            with Vertical(id="rail"):
                with Vertical(id="decisions-box"):
                    yield Static("JEV · РЕШЕНИЕ", classes="section-title")
                    with VerticalScroll(id="decisions-scroll"):
                        yield Static(id="decisions")
                with Vertical(id="evidence-box"):
                    yield Static("ПРОВЕРКИ И ФАЙЛЫ", classes="section-title")
                    with VerticalScroll(id="evidence-scroll"):
                        yield Static(id="evidence")
        yield Static(id="status")
        with Vertical(id="composer"):
            yield PromptEditor(id="prompt", soft_wrap=True, tab_behavior="focus")
            with Horizontal(id="composer-actions"):
                yield Static("Вставьте сообщение целиком\nEnter — новая строка · F4 — развернуть", id="prompt-meta")
                yield Button("Отправить · Ctrl+D", id="send-prompt")
        yield Static("Jev решает · исполнитель действует · harness проверяет · события сохраняются", id="hint")
        yield Footer()

    def on_mount(self) -> None:
        self._view = self.screen
        self._responsive(self.size.width, self.size.height)
        self._clock = self.set_interval(0.25, self._refresh_status)
        self._refresh_all()
        self._chat("SYSTEM", "Jev + Harness\n" + str(self.session.workspace) +
                   "\nНапишите задачу или нажмите F2, чтобы вставить пример.", MUTED)
        prior = self.replay_events if self.is_replay else self.session.events()
        for event in prior or []:
            self._receive(event)
        if self.is_replay:
            self._chat("REPLAY", "Сохранённые события · инструменты и API не запускаются.", YELLOW)
        editor = self._view.query_one("#prompt", PromptEditor)
        editor.border_title = "СООБЩЕНИЕ · можно вставить несколько абзацев"
        editor.focus()
        if self.initial_prompt and not self.is_replay:
            editor.load_text(self.initial_prompt)
        self.call_after_refresh(self._resize_prompt)

    def _ui_active(self) -> bool:
        # Textual shuts the App message pump before pruning Screen children.
        # Screen.is_mounted alone remains true during that pruning window.
        return bool(self.is_running and self._view is not None
                    and self._view.is_running)

    def on_unmount(self) -> None:
        if self._clock is not None:
            self._clock.stop()
            self._clock = None
        if self._busy or self.session.busy:
            self.session.cancel()

    def on_resize(self, event: events.Resize) -> None:
        self._responsive(event.size.width, event.size.height)
        self.call_after_refresh(self._resize_prompt)

    def _responsive(self, width: int, height: int) -> None:
        view = self._view if self._view is not None else self.screen
        view.set_class(width < 100, "narrow")
        view.set_class(height < 32, "short")

    def _chat(self, role: str, text: Any, color: str = CREAM) -> None:
        if not self._ui_active():
            return
        role = {"SYSTEM": "СИСТЕМА", "YOU": "ВЫ", "PLAN": "ПЛАН",
                "CHECKS": "ПРОВЕРКИ", "ERROR": "ОШИБКА", "WORKER": "ИСПОЛНИТЕЛЬ",
                "SESSION STATUS": "СОСТОЯНИЕ СЕССИИ", "LATEST JEV": "ПОСЛЕДНИЙ ОТВЕТ JEV",
                "SCREENSHOT SAVED": "СНИМОК СОХРАНЁН", "REPLAY": "ЗАПИСЬ"}.get(role, role)
        line = Text("\n" + role + "\n", style=f"bold {color}")
        line.append(plain(text), style=CREAM)
        self._view.query_one("#chat", RichLog).write(line)

    def emit(self, event: Dict[str, Any]) -> None:
        self.post_message(EventArrived(event))

    def on_event_arrived(self, message: EventArrived) -> None:
        if self._ui_active():
            self._receive(message.event)

    def _receive(self, event: Dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        seq = event.get("seq")
        if seq is not None:
            if seq in self._seen_sequences:
                return
            self._seen_sequences.add(seq)
        kind = str(event.get("type", "event"))
        data = event.get("data") or {}
        if not isinstance(data, dict):
            data = {"value": data}
        self._event_count += 1
        self._event_types.append(kind)
        self._event_types = self._event_types[-4000:]
        self._elapsed_ms = max(self._elapsed_ms, number(event.get("elapsed_ms")))
        stamp = "#{} {:7.2f}s {}".format(seq if seq is not None else self._event_count,
                                        number(event.get("elapsed_ms")) / 1000, kind.upper())
        log = Text(stamp + "\n", style=f"bold {PINK}")
        log.append(plain(data), style=MUTED)
        self._view.query_one("#event-log", RichLog).write(log)
        if kind == "user":
            self._elapsed_ms = number(event.get("elapsed_ms"))
            self._meters = {}
            self._phases = {}
            self._steps = []
            self._checks = {}
            self._acceptance_scope = ""
            self._files = []
            self._detail = ""
            self._latest_jev = {}
            self._outcome = "running" if not self.is_replay else "replay"
            self._chat("YOU", data.get("text", ""), PINK)
        elif kind == "phase":
            name = str(data.get("name", "phase"))
            self._phases[name] = data
            self._detail = plain(data.get("detail") or name, 200)
        elif kind == "plan":
            self._steps = data.get("steps") or []
            self._chat("PLAN", "\n".join("{}. {}".format(step.get("id", i + 1), step.get("title", ""))
                                        for i, step in enumerate(self._steps) if isinstance(step, dict)), MUTED)
        elif kind == "jev":
            self._latest_jev = data
            brief = plain(data.get("purpose", "Структурированное решение"), 200)
            for qid, answer in (data.get("answers") or {}).items():
                if isinstance(answer, dict):
                    value = answer.get("choice", answer.get("noul", answer.get("score", "—")))
                    brief += "\n{} → {}".format(qid, value)
                    if answer.get("confidence") is not None:
                        brief += " · confidence {:.2f}".format(number(answer["confidence"]))
            self._chat("JEV", brief, PINK)
        elif kind == "tool":
            command = plain(data.get("command", data.get("kind", "tool")), 700)
            state = str(data.get("status", ""))
            output = plain(data.get("output", ""), 2200)
            self._chat("ИНСТРУМЕНТ · " + state.upper(), command + ("\n" + output if output else ""), MUTED)
        elif kind == "message":
            self._chat(str(data.get("role", "worker")).upper(), data.get("text", ""), GREEN)
        elif kind == "checks":
            self._checks = data
            self._chat("CHECKS", "{} / {} пройдено\n".format(data.get("passed", "?"), data.get("total", "?")) +
                       "\n".join(("✓ " if item.get("passed") else "× ") + str(item.get("title", item.get("id", "check")))
                                 for item in data.get("items", []) if isinstance(item, dict)), GREEN)
        elif kind == "files":
            self._files = data.get("changed") or []
        elif kind == "meters":
            self._meters.update(data)
        elif kind == "end":
            final_meters = data.get("meters")
            if isinstance(final_meters, dict):
                self._meters.update(final_meters)
            self._outcome = str(data.get("status", "ended"))
            self._detail = plain(reason_label(str(data.get("reason", ""))), 200)
            self._acceptance_scope = plain(data.get("acceptance_scope", ""), 2000)
            self._chat(status_label(self._outcome).upper(), data.get("summary") or self._detail or "Ход завершён.",
                       GREEN if self._outcome in ("complete", "completed", "success", "accepted", "ready", "answered") else YELLOW)
            if self._acceptance_scope:
                self._chat("ГРАНИЦЫ ПРИЁМКИ", self._acceptance_scope, YELLOW)
        elif kind == "error":
            self._outcome = "error"
            self._chat("ERROR", data.get("message", "Неизвестная ошибка"), YELLOW)
        self._refresh_all()

    def _refresh_all(self) -> None:
        if not self._ui_active():
            return
        self._render_graph()
        self._render_decisions()
        self._render_evidence()
        self._refresh_status()

    def _render_graph(self) -> None:
        graph = Text()
        if not self._phases and not self._steps:
            graph.append("○  Ожидаю задачу\n", style=MUTED)
            graph.append("   Здесь появятся реальные этапы.", style=MUTED)
        phase_limit = 3 if self.size.height < 32 or self.size.width < 100 else 8
        visible_phases = list(self._phases.items())[-phase_limit:]
        for i, (name, phase) in enumerate(visible_phases):
            state = str(phase.get("status", ""))
            done = state in ("done", "complete", "completed", "success", "passed")
            bad = state in ("failed", "error", "stopped", "cancelled")
            symbol = "✓" if done else "×" if bad else "●" if state in ("running", "active", "started") else "○"
            color = GREEN if done else YELLOW if bad else PINK
            connector = "└─▶ " if i == len(visible_phases) - 1 else "├─▶ "
            graph.append(connector + symbol + "  " + name, style=f"bold {color}")
            graph.append("  " + state + "\n", style=MUTED)
        if self._steps and not self._phases:
            graph.append("План · намеченные шаги\n", style=MUTED)
            for step in self._steps:
                if isinstance(step, dict):
                    graph.append("  · {}  {}\n".format(step.get("id", ""), plain(step.get("title", ""), 180)), style=CREAM)
        self._view.query_one("#graph", Static).update(graph)

    def _render_decisions(self) -> None:
        data = self._latest_jev
        out = Text()
        if not data:
            out.append("Ответа Jev пока нет.\n\n", style=MUTED)
            out.append("Choice → выбор варианта\nScore  → уровень по шкале\nNoul   → степень истинности", style=MUTED)
        else:
            out.append(plain(data.get("purpose", "Решение"), 300) + "\n", style=f"bold {CREAM}")
            out.append(plain(data.get("model", "Jev"), 80) + " · " +
                       "{:.0f} ms\n".format(number(data.get("elapsed_ms"))), style=MUTED)
            for qid, answer in (data.get("answers") or {}).items():
                if not isinstance(answer, dict):
                    continue
                out.append("\n" + str(qid) + "\n", style=f"bold {PINK}")
                value = answer.get("choice", answer.get("noul", answer.get("score", "—")))
                out.append(str(value), style=f"bold {CREAM}")
                if answer.get("confidence") is not None:
                    out.append("  confidence {:.2f}".format(number(answer["confidence"])), style=MUTED)
                out.append("\n")
                probabilities = answer.get("probabilities") or answer.get("distribution") or {}
                if isinstance(probabilities, dict):
                    for option, probability in sorted(probabilities.items(), key=lambda item: number(item[1]), reverse=True):
                        p = min(1.0, max(0.0, number(probability)))
                        width = 13
                        filled = round(p * width)
                        out.append(plain(option, 35) + "\n", style=CREAM)
                        out.append("█" * filled, style=PINK)
                        out.append("░" * (width - filled), style="#393447")
                        out.append(" {:5.1f}%\n".format(p * 100), style=MUTED)
            out.append("\nConfidence — поле ответа; полоски показывают распределение.", style=MUTED)
        self._view.query_one("#decisions", Static).update(out)

    def _render_evidence(self) -> None:
        out = Text()
        if self._checks:
            out.append("{} / {} проверок пройдено\n".format(self._checks.get("passed", "?"), self._checks.get("total", "?")),
                       style=f"bold {GREEN}")
            for item in self._checks.get("items", []):
                if not isinstance(item, dict):
                    continue
                success = bool(item.get("passed"))
                out.append(("✓ " if success else "× ") + plain(item.get("title", item.get("id", "check")), 180) + "\n",
                           style=GREEN if success else YELLOW)
            if self._checks.get("snapshot"):
                out.append("snapshot " + plain(self._checks["snapshot"], 70) + "\n", style=MUTED)
        else:
            out.append("Проверки ещё не выполнялись.\n", style=MUTED)
        if self._acceptance_scope:
            out.append("\nГраницы приёмки\n", style=f"bold {YELLOW}")
            out.append(self._acceptance_scope + "\n", style=YELLOW)
        out.append("\nИзменённые файлы\n", style=f"bold {PINK}")
        if self._files:
            for filename in self._files[:30]:
                out.append("  " + plain(filename, 180) + "\n", style=CREAM)
            if len(self._files) > 30:
                out.append("  +{} ещё в журнале\n".format(len(self._files) - 30), style=MUTED)
        else:
            out.append("  Изменений пока нет.\n", style=MUTED)
        out.append("\nАртефакты\n", style=f"bold {PINK}")
        out.append(str(self.session.directory), style=MUTED)
        self._view.query_one("#evidence", Static).update(out)

    def _refresh_status(self) -> None:
        if not self._ui_active():
            return
        elapsed = self._elapsed_ms / 1000
        if self._busy and self._turn_started is not None:
            elapsed = max(elapsed, time.monotonic() - self._turn_started)
        mode = "ЗАПИСЬ" if self.is_replay else "LIVE"
        top = Text("JEV", style=f"bold {PINK}")
        top.append(" + HARNESS", style=f"bold {CREAM}")
        top.append("   /   " + mode + "   /   " + ("РАБОТАЕТ" if self._busy else status_label(self._outcome).upper()), style=MUTED)
        top.append("\n" + str(self.session.workspace), style=MUTED)
        self._view.query_one("#masthead", Static).update(top)
        status = Text("● " if self._busy else "○ ", style=PINK if self._busy else MUTED)
        status.append("{:5.1f}s  ".format(elapsed), style=CREAM)
        if self._meters.get("usage_complete") is False:
            status.append("usage неполный · ", style=f"bold {YELLOW}")
        status.append("Jev {}  ·  worker {}  ·  проверок {}  ·  событий {}".format(
            self._meters.get("jev_calls", 0), self._meters.get("worker_calls", 0),
            self._meters.get("checks", 0), self._event_count), style=MUTED)
        tokens = self._meters.get("jev_tokens")
        if tokens is not None:
            status.append("  ·  Jev tokens " + plain(tokens, 100), style=MUTED)
        worker_tokens = self._meters.get("worker_tokens")
        if worker_tokens is not None:
            status.append("  ·  worker tokens " + plain(worker_tokens, 100), style=MUTED)
        status.append("\n" + (self._detail or "Сессия " + str(self.session.id)), style=MUTED)
        self._view.query_one("#status", Static).update(status)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "prompt":
            self.call_after_refresh(self._resize_prompt)

    def _resize_prompt(self) -> None:
        if not self._ui_active():
            return
        editor = self._view.query_one("#prompt", PromptEditor)
        rows = max(1, editor.wrapped_document.height)
        editor.styles.height = "1fr" if self._expanded_input else min(
            max(5, rows + 2), max(5, self.size.height // 2 - 3))
        lines = len(editor.text.split("\n")) if editor.text else 0
        self._view.query_one("#prompt-meta", Static).update(
            "{} строк · {} символов\nEnter — новая строка · F4 — {}".format(
                lines, len(editor.text), "свернуть" if self._expanded_input else "развернуть"))

    def action_expand_input(self) -> None:
        if not self._ui_active() or self.screen is not self._view:
            return
        self._expanded_input = not self._expanded_input
        self._view.set_class(self._expanded_input, "input-expanded")
        self._resize_prompt()
        self._view.query_one("#prompt", PromptEditor).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-prompt":
            event.stop()
            self.action_submit_prompt()

    def action_submit_prompt(self) -> None:
        if not self._ui_active() or self.screen is not self._view:
            return
        editor = self._view.query_one("#prompt", PromptEditor)
        prompt = editor.text
        if not prompt.strip():
            return
        editor.load_text("")
        if self._expanded_input and not (self._busy or self.session.busy):
            self.action_expand_input()
        editor.focus()
        self._submit(prompt)

    def _submit(self, prompt: str) -> None:
        if prompt.startswith("/"):
            command = prompt.split()[0].lower()
            if command in ("/help", "/menu"):
                self.action_help()
            elif command == "/example":
                self.action_example()
            elif command == "/status":
                self._chat("SESSION STATUS", self.session.status(), MUTED)
                self._chat("LATEST JEV", self._latest_jev or "Ответа пока нет", PINK)
            elif command == "/stop":
                self._stop()
            elif command == "/clear":
                self._view.query_one("#chat", RichLog).clear()
                self._view.query_one("#event-log", RichLog).clear()
                self._chat("SYSTEM", "Экран очищен. События сохранены на диске.", MUTED)
            elif command in ("/quit", "/exit"):
                if self._busy:
                    self._stop()
                    self._chat("SYSTEM", "Останавливаю. Повторите /quit после завершения задачи.", MUTED)
                else:
                    self.exit()
            else:
                self._chat("SYSTEM", "Неизвестная команда. Список команд: /help.", YELLOW)
            return
        if self.is_replay:
            self._chat("REPLAY", "Это просмотр записи. Для новой задачи запустите обычную сессию.", YELLOW)
            return
        if self._busy or self.session.busy:
            self._view.query_one("#prompt", PromptEditor).load_text(prompt)
            self._chat("SYSTEM", "Задача выполняется. Следующее сообщение сохранено во вводе; /stop — остановить.", YELLOW)
            return
        self._busy = True
        self._outcome = "running"
        self._turn_started = time.monotonic()
        self._elapsed_ms = 0
        self._refresh_status()
        self._runner = self.run_worker(self._run_turn(prompt), name="agent-turn", exclusive=True,
                                       exit_on_error=False)

    async def _run_turn(self, prompt: str) -> None:
        try:
            result = await self.session.run_turn(prompt, self.emit)
            # Session owns the outcome event. This fallback only handles adapters
            # that return a result but do not emit an end/error event.
            await asyncio.sleep(0)
            if self._outcome == "running":
                self._outcome = str((result or {}).get("status", "ended"))
        except asyncio.CancelledError:
            self.session.cancel()
            self._outcome = "cancelled"
            raise
        except Exception as exc:
            self._outcome = "error"
            self._chat("ERROR", "{}: {}".format(type(exc).__name__, plain(str(exc), 2000)), YELLOW)
        finally:
            self._busy = False
            self._refresh_all()
            if self._ui_active():
                self._view.query_one("#prompt", PromptEditor).focus()

    def _stop(self) -> None:
        if self._busy or self.session.busy:
            self.session.cancel()
            self._detail = "Остановка запрошена; жду завершения работающего процесса."
            self._chat("SYSTEM", self._detail, YELLOW)
        else:
            self._chat("SYSTEM", "Сейчас ни одна задача не выполняется.", MUTED)

    def action_stop_or_quit(self) -> None:
        if self._busy or self.session.busy:
            self._stop()
        else:
            self.exit()

    def action_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
            return
        self.push_screen(HelpScreen(), callback=lambda _: self._view.query_one("#prompt", PromptEditor).focus())

    def action_example(self) -> None:
        prompt = self._view.query_one("#prompt", PromptEditor)
        example = getattr(self.session, "example_prompt", "") or EXAMPLE_PROMPT
        prompt.load_text(example)
        prompt.move_cursor((0, 0))
        prompt.focus()

    def action_toggle_events(self) -> None:
        self._show_events = not self._show_events
        self._view.query_one("#chat", RichLog).display = not self._show_events
        self._view.query_one("#event-log", RichLog).display = self._show_events
        self._view.query_one("#stream-title", Static).update(
            "ЖУРНАЛ СОБЫТИЙ · СОХРАНЁН НА ДИСКЕ" if self._show_events else "ДИАЛОГ")

    def action_save_view(self) -> None:
        directory = Path(self.session.directory) / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        filename = directory / ("terminal-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".svg")
        filename.write_text(self.export_screenshot(title="Jev + Harness · " + str(self.session.id)), encoding="utf-8")
        self._chat("SCREENSHOT SAVED", str(filename), GREEN)
        self.notify("Снимок терминала SVG сохранён", timeout=3)
