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
from textual.widgets import Button, Footer, RichLog, Static, TabbedContent, TabPane, TextArea

from .ui_widgets import (AMBER, CREAM, MUTED, GREEN, RED, ArtifactScreen,
                         ConversationCard, HelpScreen, PickerScreen, PromptEditor,
                         ToolCard, plain)

YELLOW = AMBER

EXAMPLE_PROMPT = (
    "Создай CLI-анализатор инцидентов: читай JSONL, группируй ошибки по сервису и причине, "
    "убирай дубли event_id, правильно сравнивай часовые пояса и пропускай битые строки "
    "с предупреждением. Добавь пример данных, JSON- и Markdown-отчёт, тесты. "
    "Запусти тесты и покажи готовую команду запуска."
)


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
        "response_prepared_without_independent_acceptance": "Результат подготовлен; выполненные проверки — в деталях F6.",
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


class JevApp(App):
    """Live terminal conversation with an independently testable session."""

    TITLE = "Jev + Harness"
    SUB_TITLE = "Реальные решения · реальные инструменты · сохранённые доказательства"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+d", "submit_prompt", "Отправить", priority=True),
        Binding("ctrl+enter", "submit_prompt", "Отправить", priority=True, show=False),
        Binding("f1,ctrl+p", "palette", "Команды", priority=True),
        Binding("f6", "toggle_details", "Детали", priority=True),
        Binding("f2", "example", "Пример", priority=True),
        Binding("f3", "toggle_events", "Журнал", priority=True),
        Binding("f4", "expand_input", "Развернуть ввод", priority=True),
        Binding("ctrl+s", "save_view", "Снимок", priority=True),
        Binding("ctrl+c", "stop_or_quit", "Стоп / выход", priority=True),
    ]
    CSS = """
    Screen { background: #181b17; color: #e8e4da; }
    #masthead { height: 3; padding: 0 3; background: #1f231d; border-bottom: solid #343b30; }
    #body { height: 1fr; padding: 0 2; }
    #main { width: 1fr; min-width: 24; }
    #phase-strip { height: 1; margin: 1 1 0 1; color: #999b94; }
    #chat { height: 1fr; padding: 0 2 1 1; scrollbar-size: 1 1; }
    #welcome { height: auto; padding: 2 1; color: #999b94; }
    .conversation-card { height: auto; margin-top: 1; padding: 0 1; }
    .message-role { height: 1; margin-bottom: 1; }
    .message-body { height: auto; }
    .conversation-card.user { background: #24291f; border-left: thick #d8ad73; padding: 1 2; }
    .conversation-card.notice { border-left: solid #47503e; }
    .conversation-card.notice .message-role { margin-bottom: 0; }
    .conversation-card.jev { border-left: solid #d8ad73; }
    .conversation-card.jev .message-role { margin-bottom: 0; }
    ToolCard { height: auto; margin-top: 1; padding: 0; border: none;
        background: #20251d; color: #999b94; }
    ToolCard CollapsibleTitle { width: 1fr; color: #b7bcae; padding: 0 1; background: #20251d; }
    ToolCard CollapsibleTitle:focus { background: #343c2b; }
    ToolCard.tool-failed CollapsibleTitle { color: #d99383; }
    ToolCard.tool-done CollapsibleTitle { color: #a7b995; }
    ToolCard Contents { padding: 1 2; }
    .tool-output { height: auto; }
    #rail { display: none; width: 46; min-width: 30; margin-left: 1;
        border-left: solid #343b30; background: #1d211a; }
    #drawer-title { height: 2; padding: 0 1; color: #d8ad73; }
    #details-tabs { height: 1fr; }
    #details-tabs TabPane { height: 1fr; padding: 0 1; }
    .detail-scroll { height: 1fr; scrollbar-size: 1 1; }
    #graph, #decisions, #evidence { height: auto; }
    #graph { margin: 1 0; }
    #event-log { height: 1fr; scrollbar-size: 1 1; padding: 0; }
    Tabs { background: #1d211a; }
    Tab { color: #999b94; }
    Tab.-active { color: #d8ad73; }
    Underline > .underline--bar { color: #d8ad73; background: #1d211a; }
    #status { height: 1; padding: 0 3; color: #999b94; }
    #composer { height: auto; margin: 0 2; }
    #prompt { height: 5; border: round #555f49; background: #22271e;
        padding: 0 1; scrollbar-size: 1 1; }
    #prompt:focus { border: round #d8ad73; }
    #composer-actions { height: 3; align-vertical: middle; }
    #prompt-meta { width: 1fr; height: 2; color: #999b94; padding-left: 1; }
    #send-prompt { width: 23; min-width: 20; height: 3;
        background: #303b26; color: #e8e4da; border: round #555f49; }
    #send-prompt:hover { background: #404f31; }
    Screen.input-expanded #body, Screen.input-expanded #status { display: none; }
    Screen.input-expanded #composer { height: 1fr; }
    Footer { background: #1f231d; color: #999b94; }
    Footer > .footer--key { background: #30382a; color: #d8ad73; }
    Screen.narrow #body { padding: 0 1; }
    Screen.narrow #rail { width: 1fr; margin-left: 0; border-left: none; }
    Screen.narrow.details-open #main { display: none; }
    Screen.short #masthead { height: 2; border-bottom: none; }
    Screen.short #phase-strip { margin-top: 0; }
    Screen.short #composer { margin: 0 1; }
    Screen.short #welcome { padding: 1; }
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
        self._source_context: Dict[str, Any] = {}
        self._checks: Dict[str, Any] = {}
        self._acceptance_scope = ""
        self._files = []
        self._meters: Dict[str, Any] = {}
        self._outcome = "idle"
        self._detail = ""
        self._elapsed_ms = 0.0
        self._turn_started = None
        self._show_events = False
        self._show_details = False
        self._tools = {}
        self._restoring = False
        self._draft_timer = None
        self._latest_draft = ""
        self._last_worker_text = ""
        self._expanded_input = False
        self._seen_sequences = set()
        self._runner = None
        self._view = None
        self._clock = None

    def compose(self) -> ComposeResult:
        yield Static(id="masthead")
        with Horizontal(id="body"):
            with Vertical(id="main"):
                yield Static(id="phase-strip")
                with VerticalScroll(id="chat"):
                    yield Static(Text("Начните с задачи.\n\nСоздать инструмент, разобраться в проекте, проверить гипотезу.\n"
                                      "Здесь появятся ответы, решения Jev и реальные действия.\n\n"
                                      "F2 — пример запроса     F1 — все команды", style=MUTED), id="welcome")
            with Vertical(id="rail"):
                yield Static("НАБЛЮДЕНИЕ  /  F6 закрыть", id="drawer-title")
                with TabbedContent(id="details-tabs"):
                    with TabPane("Jev", id="decision-tab"):
                        with VerticalScroll(classes="detail-scroll"):
                            yield Static(id="graph")
                            yield Static(id="decisions")
                    with TabPane("Проверки", id="evidence-tab"):
                        with VerticalScroll(classes="detail-scroll"):
                            yield Static(id="evidence")
                    with TabPane("События", id="events-tab"):
                        yield RichLog(id="event-log", markup=False, highlight=False,
                                      wrap=True, min_width=20, max_lines=4000)
        yield Static(id="status")
        with Vertical(id="composer"):
            yield PromptEditor(id="prompt", soft_wrap=True, tab_behavior="focus")
            with Horizontal(id="composer-actions"):
                yield Static(id="prompt-meta")
                yield Button("Отправить · Ctrl+D", id="send-prompt")
        yield Footer()

    def on_mount(self) -> None:
        self._view = self.screen
        self._responsive(self.size.width, self.size.height)
        self._clock = self.set_interval(0.25, self._refresh_status)
        self._restore_history()
        editor = self._view.query_one("#prompt", PromptEditor)
        editor.border_title = " Сообщение "
        editor.focus()
        if not self.is_replay:
            from .catalog import load_draft
            editor.load_text(self.initial_prompt if self.initial_prompt is not None else load_draft(self.session))
        self.call_after_refresh(self._resize_prompt)

    def _restore_history(self) -> None:
        self._restoring = True
        prior = self.replay_events if self.is_replay else self.session.events()
        for event in prior or []:
            self._receive(event)
        if self.is_replay:
            self._chat("REPLAY", "Сохранённые события · инструменты и API не запускаются.", YELLOW)
        elif prior:
            self._chat("SYSTEM", "История восстановлена. Новое сообщение продолжит эту сессию.", MUTED)
        self._restoring = False
        self._refresh_all()
        self.call_after_refresh(self._scroll_chat)

    def _scroll_chat(self) -> None:
        if self._ui_active():
            self._view.query_one("#chat", VerticalScroll).scroll_end(animate=False)

    def _ui_active(self) -> bool:
        # Textual shuts the App message pump before pruning Screen children.
        # Screen.is_mounted alone remains true during that pruning window.
        return bool(self.is_running and self._view is not None
                    and self._view.is_running)

    def on_unmount(self) -> None:
        self._persist_draft()
        if self._draft_timer is not None:
            self._draft_timer.stop()
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
        original = role
        role = {"SYSTEM": "СИСТЕМА", "YOU": "ВЫ", "PLAN": "ПЛАН",
                "CHECKS": "ПРОВЕРКИ", "ERROR": "ОШИБКА", "WORKER": "АГЕНТ",
                "ASSISTANT": "АГЕНТ", "SESSION STATUS": "СЕССИЯ", "LATEST JEV": "ПОСЛЕДНИЙ ОТВЕТ JEV",
                "SCREENSHOT SAVED": "СНИМОК СОХРАНЁН", "REPLAY": "ЗАПИСЬ"}.get(role, role)
        self._hide_welcome()
        kind = "user" if original == "YOU" else "jev" if original == "JEV" else "message" if original in ("WORKER", "ASSISTANT") else "notice"
        card = ConversationCard(role, plain(text), color, markdown=original in ("WORKER", "ASSISTANT"), kind=kind)
        chat = self._view.query_one("#chat", VerticalScroll)
        follow = chat.is_vertical_scroll_end or original == "YOU"
        chat.mount(card)
        if not self._restoring and follow:
            self.call_after_refresh(self._scroll_chat)

    def _hide_welcome(self) -> None:
        for widget in self._view.query("#welcome"):
            widget.display = False

    def _tool(self, event: Dict[str, Any], data: Dict[str, Any]) -> None:
        self._hide_welcome()
        # call_id identifies an attempt/check; item_id identifies a provider tool.
        # Missing identities must never merge unrelated legacy log events.
        identity = data.get("call_id") or "turn-{}".format(event.get("turn", "legacy"))
        item = data.get("item_id") or "event-{}".format(event.get("seq", self._event_count))
        key = (identity, item)
        chat = self._view.query_one("#chat", VerticalScroll)
        follow = chat.is_vertical_scroll_end
        if key not in self._tools:
            self._tools[key] = ToolCard(data)
            chat.mount(self._tools[key])
        else:
            self._tools[key].update_event(data)
        if not self._restoring and follow:
            self.call_after_refresh(self._scroll_chat)

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
        log = Text(stamp + "\n", style=f"bold {AMBER}")
        log.append(plain(data), style=MUTED)
        self._view.query_one("#event-log", RichLog).write(log)
        if kind == "user":
            self._last_worker_text = ""
            self._elapsed_ms = number(event.get("elapsed_ms"))
            self._meters = {}
            self._phases = {}
            self._steps = []
            self._checks = {}
            self._acceptance_scope = ""
            self._files = []
            self._detail = ""
            self._latest_jev = {}
            self._source_context = {}
            self._outcome = "running" if not self.is_replay else "replay"
            self._chat("YOU", data.get("text", ""), AMBER)
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
            if data.get("applied") is False:
                brief += "\nНаблюдение · решение не применяется"
            self._chat("JEV", brief, AMBER)
        elif kind == "tool":
            self._tool(event, data)
        elif kind == "context":
            self._source_context = data
            paths = data.get("selected") or []
            brief = "{} фрагментов · {} · {} файлов просмотрено".format(
                len(paths), data.get("selection", "context"), data.get("files_scanned", "?"))
            if paths:
                brief += "\n" + ", ".join(plain(item, 140) for item in paths[:8])
            if data.get("partial"):
                brief += " · выборка ограничена"
            self._chat("КОНТЕКСТ", brief, MUTED)
        elif kind == "triage":
            self._chat("РАЗБОР ПРОВЕРКИ", data.get("summary") or data, YELLOW)
        elif kind == "policy":
            self._chat("РЕЖИМ", data.get("summary") or data.get("message") or data, MUTED)
        elif kind == "message":
            self._last_worker_text = str(data.get("text", ""))
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
            interrupted = self._outcome in ("cancelled", "stopped", "error", "failed")
            for card in self._tools.values():
                if not card.is_terminal:
                    card.update_event({"status": "stopped" if interrupted else "unknown"})
            self._detail = plain(reason_label(str(data.get("reason", ""))), 200)
            self._acceptance_scope = plain(data.get("acceptance_scope", ""), 2000)
            summary = data.get("summary")
            if summary == self._last_worker_text:
                summary = self._detail
            self._chat(status_label(self._outcome).upper(), summary or self._detail or "Ход завершён.",
                       GREEN if self._outcome in ("complete", "completed", "success", "accepted", "ready", "answered") else YELLOW)
            if self._acceptance_scope:
                self._chat("ГРАНИЦЫ ПРИЁМКИ", self._acceptance_scope, YELLOW)
        elif kind == "error":
            self._outcome = "error"
            for card in self._tools.values():
                if not card.is_terminal:
                    card.update_event({"status": "stopped"})
            self._chat("ERROR", data.get("message", "Неизвестная ошибка"), YELLOW)
        if not self._restoring:
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
        phase_limit = 12
        visible_phases = list(self._phases.items())[-phase_limit:]
        for i, (name, phase) in enumerate(visible_phases):
            state = str(phase.get("status", ""))
            done = state in ("done", "complete", "completed", "success", "passed")
            bad = state in ("failed", "error", "stopped", "cancelled")
            symbol = "✓" if done else "×" if bad else "●" if state in ("running", "active", "started") else "○"
            color = GREEN if done else YELLOW if bad else AMBER
            connector = "└─▶ " if i == len(visible_phases) - 1 else "├─▶ "
            graph.append(connector + symbol + "  " + name, style=f"bold {color}")
            graph.append("  " + state + "\n", style=MUTED)
        if self._steps and not self._phases:
            graph.append("План · намеченные шаги\n", style=MUTED)
            for step in self._steps:
                if isinstance(step, dict):
                    graph.append("  · {}  {}\n".format(step.get("id", ""), plain(step.get("title", ""), 180)), style=CREAM)
        self._view.query_one("#graph", Static).update(graph)
        ribbon = Text()
        for i, (name, phase) in enumerate(list(self._phases.items())[-4:]):
            if i:
                ribbon.append("  →  ", style=MUTED)
            state = phase.get("status")
            done = state in ("done", "complete", "completed", "success", "passed")
            bad = state in ("failed", "error", "stopped", "cancelled")
            active = state in ("running", "active", "started")
            symbol = "✓ " if done else "× " if bad else "● " if active else "○ "
            ribbon.append(symbol + plain(name, 32), style=GREEN if done else AMBER if bad or active else MUTED)
        if not self._phases:
            ribbon.append("○  Готов к задаче   ·   действия появятся после отправки", style=MUTED)
        self._view.query_one("#phase-strip", Static).update(ribbon)

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
                label = plain(qid, 100)
                if data.get("purpose") == "context":
                    candidate = next((item for item in (self._source_context.get("candidates") or [])
                                      if isinstance(item, dict) and item.get("id") == qid), None)
                    if candidate and candidate.get("path"):
                        label = plain(candidate["path"], 180)
                        first, last = candidate.get("start_line"), candidate.get("end_line")
                        if isinstance(first, int) and not isinstance(first, bool) and first > 0:
                            label += ":" + str(first)
                            if isinstance(last, int) and not isinstance(last, bool) and last > first:
                                label += "–" + str(last)
                        label += " ({})".format(plain(qid, 100))
                out.append("\n" + label + "\n", style=f"bold {AMBER}")
                value = answer.get("choice", answer.get("noul", answer.get("score", "—")))
                out.append(("Noul " if "noul" in answer else "") + str(value), style=f"bold {CREAM}")
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
                        out.append("█" * filled, style=AMBER)
                        out.append("░" * (width - filled), style="#3d4535")
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
        out.append("\nИзменённые файлы\n", style=f"bold {AMBER}")
        if self._files:
            for filename in self._files[:30]:
                out.append("  " + plain(filename, 180) + "\n", style=CREAM)
            if len(self._files) > 30:
                out.append("  +{} ещё в журнале\n".format(len(self._files) - 30), style=MUTED)
        else:
            out.append("  Изменений пока нет.\n", style=MUTED)
        out.append("\nАртефакты\n", style=f"bold {AMBER}")
        out.append(str(self.session.directory), style=MUTED)
        self._view.query_one("#evidence", Static).update(out)

    def _refresh_status(self) -> None:
        if not self._ui_active():
            return
        elapsed = self._elapsed_ms / 1000
        if self._busy and self._turn_started is not None:
            elapsed = max(elapsed, time.monotonic() - self._turn_started)
        mode = "ЗАПИСЬ" if self.is_replay else "РАБОТАЕТ" if self._busy else "ОЖИДАНИЕ"
        execution_mode = getattr(self.session, "execution_mode", "auto")
        jev_mode = getattr(self.session, "jev_mode", "assist")
        top = Text("JEV", style=f"bold {AMBER}")
        top.append(" / HARNESS", style=f"bold {CREAM}")
        top.append("   " + mode + "   ·   " + execution_mode + "   ·   jev " + jev_mode, style=MUTED)
        if not self._busy:
            top.append("   ·   " + status_label(self._outcome).lower(), style=GREEN)
        if self.size.height >= 32:
            top.append("\n" + plain(str(self.session.workspace), 180), style=MUTED)
        self._view.query_one("#masthead", Static).update(top)
        status = Text("● " if self._busy else "○ ", style=AMBER if self._busy else MUTED)
        status.append("{:5.1f}s  ".format(elapsed), style=CREAM)
        if self._meters.get("usage_complete") is False:
            status.append("usage неполный · ", style=f"bold {YELLOW}")
        status.append("Jev {}  ·  worker {}  ·  проверок {}  ·  событий {}".format(
            self._meters.get("jev_calls", 0), self._meters.get("worker_calls", 0),
            self._meters.get("checks", 0), self._event_count), style=MUTED)
        if self.size.width >= 110 and self._detail:
            status.append("  /  " + plain(self._detail, 70), style=MUTED)
        self._view.query_one("#status", Static).update(status)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "prompt":
            self._latest_draft = event.text_area.text
            self.call_after_refresh(self._resize_prompt)
            if not self.is_replay:
                if self._draft_timer is not None:
                    self._draft_timer.stop()
                self._draft_timer = self.set_timer(.3, self._persist_draft)

    def _persist_draft(self) -> None:
        if self.is_replay or self._view is None:
            return
        from .catalog import save_draft
        # Keep the last known draft even during Textual's shutdown pruning.
        editors = list(self._view.query("#prompt"))
        if editors:
            self._latest_draft = editors[0].text
        try:
            save_draft(self.session, self._latest_draft)
        except (OSError, ValueError):
            if self._ui_active():
                self.notify("Черновик не сохранён на диск · лимит 20 000 символов", severity="warning")

    def _resize_prompt(self) -> None:
        if not self._ui_active():
            return
        editor = self._view.query_one("#prompt", PromptEditor)
        rows = max(1, editor.wrapped_document.height)
        editor.styles.height = "1fr" if self._expanded_input else min(
            max(5, rows + 2), max(5, self.size.height // 2 - 3))
        lines = len(editor.text.split("\n")) if editor.text else 0
        self._view.query_one("#prompt-meta", Static).update(
            "{} строк · {} / 20 000 символов\nEnter — новая строка · F4 — {}".format(
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
        if len(prompt) > 20000:
            self.notify("Сообщение длиннее 20 000 символов. Сократите его; текст остаётся в редакторе.", severity="warning")
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
                status = self.session.status()
                if not (self._busy or self.session.busy):
                    status.update(self._meters)
                self._chat("SESSION STATUS", status, MUTED)
                self._chat("LATEST JEV", self._latest_jev or "Ответа пока нет", AMBER)
            elif command in ("/details", "/events"):
                self.action_toggle_events() if command == "/events" else self.action_toggle_details()
            elif command == "/sessions":
                self.action_sessions()
            elif command == "/files":
                self.action_files()
            elif command == "/export":
                self.action_export()
            elif command in ("/mode", "/jev"):
                parts = prompt.split()
                if len(parts) == 2:
                    self._configure("execution_mode" if command == "/mode" else "jev_mode", parts[1])
                else:
                    self._chat("SYSTEM", "/mode auto|plan   /jev assist|observe|off", MUTED)
            elif command == "/stop":
                self._stop()
            elif command == "/clear":
                self._view.query_one("#chat", VerticalScroll).remove_children()
                self._tools = {}
                self._view.query_one("#event-log", RichLog).clear()
                self._chat("SYSTEM", "Экран очищен. События сохранены на диске.", MUTED)
            elif command == "/bottom":
                self._scroll_chat()
            elif command in ("/quit", "/exit"):
                if self._busy:
                    self._stop()
                    self._chat("SYSTEM", "Останавливаю. Повторите /quit после завершения задачи.", MUTED)
                else:
                    self._persist_draft()
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
            self._persist_draft()
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

    def _details(self, show: bool, tab: Optional[str] = None) -> None:
        self._show_details = show
        self._view.query_one("#rail").display = show
        self._view.set_class(show, "details-open")
        if tab:
            self._view.query_one("#details-tabs", TabbedContent).active = tab
        self._show_events = show and self._view.query_one("#details-tabs", TabbedContent).active == "events-tab"

    def action_toggle_details(self) -> None:
        if self.screen is self._view:
            self._details(not self._show_details)

    def action_toggle_events(self) -> None:
        if self.screen is self._view:
            active = self._view.query_one("#details-tabs", TabbedContent).active
            self._details(not (self._show_details and active == "events-tab"), "events-tab")

    def _focus_editor(self) -> None:
        if self._ui_active():
            self._view.query_one("#prompt", PromptEditor).focus()

    def action_palette(self) -> None:
        if isinstance(self.screen, PickerScreen):
            self.pop_screen()
            return
        if self.screen is not self._view:
            return
        choices = [
            {"title": "Детали Jev и граф", "description": "F6 · вероятности, проверки и файлы", "value": "/details"},
            {"title": "Журнал событий", "description": "F3 · точные сохранённые данные", "value": "/events"},
            {"title": "Продолжить сессию", "description": "/sessions · поиск по предыдущим задачам", "value": "/sessions"},
            {"title": "Файлы и изменения", "description": "/files · исходный текст и diff", "value": "/files"},
            {"title": "Экспорт разговора", "description": "/export · Markdown в папке сессии", "value": "/export"},
            {"title": "Режим: план", "description": "/mode plan · только чтение", "value": "/mode plan"},
            {"title": "Режим: выполнение", "description": "/mode auto · работа с файлами", "value": "/mode auto"},
            {"title": "Jev: помощь", "description": "/jev assist · применять решения", "value": "/jev assist"},
            {"title": "Jev: наблюдение", "description": "/jev observe · оценивать без управления", "value": "/jev observe"},
            {"title": "Jev: выключить", "description": "/jev off · без вызовов Jev", "value": "/jev off"},
            {"title": "Пример задачи", "description": "F2 · вставить, не запускать", "value": "/example"},
            {"title": "Помощь и сочетания клавиш", "description": "/help", "value": "/help"},
            {"title": "Состояние сессии", "description": "/status", "value": "/status"},
        ]
        self.push_screen(PickerScreen("Команды", choices), self._palette_selected)

    def _palette_selected(self, value: Optional[str]) -> None:
        self._focus_editor()
        if value:
            self._submit(value)

    def _configure(self, name: str, value: str) -> None:
        if self.is_replay or self._busy or self.session.busy:
            self._chat("SYSTEM", "Режим можно изменить только в живой сессии, когда задача завершена.", YELLOW)
            return
        try:
            self.session.configure(**{name: value})
        except (ValueError, RuntimeError) as exc:
            self._chat("ERROR", str(exc), YELLOW)
            return
        self._chat("РЕЖИМ", "{} → {}".format("Исполнение" if name == "execution_mode" else "Jev", value), AMBER)
        self._refresh_status()

    def action_sessions(self) -> None:
        if self.is_replay or self._busy or self.session.busy:
            self._chat("SYSTEM", "Сессию можно сменить после завершения текущей задачи.", YELLOW)
            return
        from .catalog import list_sessions
        choices = [{"title": item["title"],
                    "description": "{} · {} · {} ходов".format(item["id"], item.get("status", ""), item.get("turns", 0)),
                    "value": item["directory"]} for item in list_sessions(Path(self.session.directory).parent)]
        self.push_screen(PickerScreen("Сессии", choices, "Найти задачу…"), self._session_selected)

    async def _session_selected(self, directory: Optional[str]) -> None:
        if not directory:
            self._focus_editor()
            return
        if self._busy or self.session.busy:
            return
        from .core import Session
        from .catalog import load_draft
        self._persist_draft()
        try:
            replacement = Session.load(Path(directory))
        except (OSError, ValueError, KeyError) as exc:
            self._chat("ERROR", "Не удалось открыть сессию: " + str(exc), YELLOW)
            return
        self.session = replacement
        self._seen_sequences.clear()
        self._event_count = 0
        self._event_types = []
        self._tools = {}
        self._phases, self._latest_jev, self._checks, self._meters = {}, {}, {}, {}
        self._source_context = {}
        self._steps, self._files = [], []
        self._acceptance_scope, self._detail = "", ""
        self._outcome, self._elapsed_ms, self._turn_started = "idle", 0.0, None
        self._last_worker_text = ""
        await self._view.query_one("#chat", VerticalScroll).remove_children()
        self._view.query_one("#event-log", RichLog).clear()
        self._restore_history()
        self._view.query_one("#prompt", PromptEditor).load_text(load_draft(self.session))
        self._focus_editor()

    def action_files(self) -> None:
        from .catalog import list_artifacts
        choices = [{"title": item["path"], "description": item.get("status", ""), "value": item["path"]}
                   for item in list_artifacts(self.session)]
        self.push_screen(PickerScreen("Файлы сессии", choices, "Найти файл…"), self._file_selected)

    def _file_selected(self, path: Optional[str]) -> None:
        if not path:
            self._focus_editor()
            return
        from .catalog import read_artifact
        try:
            artifact = read_artifact(self.session, path)
        except (OSError, ValueError) as exc:
            self._chat("ERROR", str(exc), YELLOW)
            return
        self.push_screen(ArtifactScreen(artifact), lambda _: self._focus_editor())

    def action_export(self) -> None:
        from .catalog import export_session
        try:
            path = export_session(self.session)
        except (OSError, ValueError) as exc:
            self._chat("ERROR", str(exc), YELLOW)
            return
        self._chat("ЭКСПОРТ", str(path), GREEN)

    def action_save_view(self) -> None:
        directory = Path(self.session.directory) / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        filename = directory / ("terminal-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".svg")
        filename.write_text(self.export_screenshot(title="Jev + Harness · " + str(self.session.id)), encoding="utf-8")
        self._chat("SCREENSHOT SAVED", str(filename), GREEN)
        self.notify("Снимок терминала SVG сохранён", timeout=3)
