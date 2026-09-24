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
from .activity import ActivityGroup

YELLOW = AMBER

EXAMPLE_PROMPT = (
    "Build a CLI incident analyser: read JSONL, group errors by service and cause, "
    "drop duplicate event_id, compare time zones correctly and skip broken lines "
    "with a warning. Add sample data, a JSON and a Markdown report, and tests. "
    "Run the tests and show the final command to run it."
)


def number(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def status_label(status: str) -> str:
    return {
        "idle": "Waiting", "running": "Working", "ready": "Result prepared",
        "accepted": "Contract checks passed", "complete": "Turn finished",
        "completed": "Turn finished", "success": "Turn finished", "ended": "Turn finished",
        "cancelled": "Stopped", "stopped": "Stopped", "blocked": "Needs data",
        "error": "Error", "failed": "Error", "replay": "Replay",
        "needs_input": "Needs clarification", "answered": "Answer prepared",
    }.get(status, status)


def reason_label(reason: str) -> str:
    return {
        "response_prepared_without_independent_acceptance": "Result prepared; the checks that ran are in the F6 details.",
        "registered_checks_passed": "All checks of the saved contract passed.",
        "checks_failed_or_no_progress": "Some checks failed, or repairs no longer make progress.",
        "iteration_limit_or_no_progress": "Attempt limit reached, or nothing changed.",
        "review_requests_clarification": "Jev asks you to clarify the task before continuing.",
        "uncertain_request_correspondence": "It is unclear whether the result matches your request.",
        "user_cancelled": "Task stopped. The files created are kept.",
    }.get(reason, reason)


class EventArrived(Message):
    """post_message also safely accepts events emitted from a worker thread."""

    def __init__(self, event: Dict[str, Any]) -> None:
        super().__init__()
        self.event = event


class JevApp(App):
    """Live terminal conversation with an independently testable session."""

    TITLE = "JEVIS"
    SUB_TITLE = "terminal agent · idea → plan → work"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+d", "submit_prompt", "Send", priority=True, show=False),
        Binding("ctrl+enter", "submit_prompt", "Send", priority=True, show=False),
        Binding("f1,ctrl+p", "palette", "Commands", priority=True),
        Binding("f6", "toggle_details", "Jev", priority=True, show=False),
        Binding("f2", "example", "Example", priority=True, show=False),
        Binding("f3", "toggle_events", "Log", priority=True, show=False),
        Binding("f4", "expand_input", "Expand input", priority=True, show=False),
        Binding("ctrl+s", "save_view", "Snapshot", priority=True, show=False),
        Binding("ctrl+c", "stop_or_quit", "Stop / quit", priority=True, show=False),
        Binding("ctrl+o", "toggle_activity", "Activity", priority=True),
        Binding("ctrl+n", "new_session", "New chat", priority=True, show=False),
        Binding("ctrl+l", "focus_prompt", "Focus input", priority=True),
        Binding("pageup", "chat_page(-1)", "Up", priority=True, show=False),
        Binding("pagedown", "chat_page(1)", "Down", priority=True, show=False),
        Binding("ctrl+end", "latest_answer", "Jump to answer", priority=True, show=False),
        Binding("f5", "open_brief", "Task", priority=True, show=False),
        Binding("escape", "back_to_chat", "Back to chat", show=False),
    ]
    CSS = """
    * { scrollbar-color: #684763; scrollbar-color-hover: #a76e98;
        scrollbar-color-active: #f2a0cc; scrollbar-background: #211a28; }
    Screen { background: #18151d; color: #eee8f1; }
    #masthead { height: 2; padding: 0 2; background: #201a27; }
    #navigation { height: 1; padding: 0 2; background: #201a27; }
    #navigation Button { min-width: 5; width: auto; height: 1; border: none; padding: 0 1;
        margin-right: 1; background: #2e2435; color: #c9bdd2; }
    #navigation Button:hover, #navigation Button:focus { background: #49324c; color: #f2a0cc; }
    #navigation #nav-new { color: #f2a0cc; }
    #body { height: 1fr; padding: 0 2; }
    #main { width: 1fr; min-width: 24; }
    #phase-strip { height: 1; margin: 1 1 0 1; color: #aaa0b2; }
    #chat { height: 1fr; padding: 0 2 1 1; scrollbar-size: 1 1; }
    #welcome { height: auto; padding: 2 1; color: #aaa0b2; }
    #welcome-example { margin: 0 1 1 1; width: auto; height: 1; border: none; background: #49324c; color: #f2a0cc; }
    .conversation-card { height: auto; margin-top: 1; padding: 0 1; }
    .message-role { height: 1; margin-bottom: 1; }
    .message-body { height: auto; }
    .conversation-card.user { background: #2a2031; border-left: solid #654968; padding: 0 1; }
    .conversation-card.notice { border-left: solid #4f3b5c; }
    .conversation-card.notice .message-role { margin-bottom: 0; }
    .conversation-card.jev { border-left: solid #f2a0cc; }
    .conversation-card.jev .message-role { margin-bottom: 0; }
    .conversation-card.answer { border-left: solid #f2a0cc; padding: 0 1; }
    .activity-group { height: auto; margin: 1 0; border: none; padding: 0; background: #211a28; }
    .activity-group > CollapsibleTitle { color: #c9a1c3; padding: 0 1; background: #2a2031; }
    .activity-group > Contents { padding: 0 1 1 1; }
    .activity-body { height: auto; }
    ToolCard { height: auto; margin-top: 1; padding: 0; border: none;
        background: #221c29; color: #aaa0b2; }
    ToolCard CollapsibleTitle { width: 1fr; color: #c9bdd2; padding: 0 1; background: #221c29; }
    ToolCard CollapsibleTitle:focus { background: #49324c; }
    ToolCard.tool-failed CollapsibleTitle { color: #ee9b9b; }
    ToolCard.tool-done CollapsibleTitle { color: #a6ccad; }
    ToolCard Contents { padding: 1 2; }
    .tool-output { height: auto; }
    #rail { display: block; width: 38; min-width: 30; margin-left: 1;
        border-left: solid #3b2d46; background: #211a28; }
    #drawer-title { height: 2; padding: 0 1; color: #f2a0cc; }
    #live-log-help { height: 2; padding: 0 1; color: #aaa0b2; background: #241d2c; }
    #details-tabs { height: 1fr; }
    #details-tabs TabPane { height: 1fr; padding: 0 1; }
    .detail-scroll { height: 1fr; scrollbar-size: 1 1; }
    #graph, #decisions, #evidence { height: auto; }
    #graph { margin: 1 0; }
    #event-log { height: 1fr; scrollbar-size: 1 1; padding: 0; }
    Tabs { background: #211a28; }
    Tab { color: #aaa0b2; }
    Tab.-active { color: #f2a0cc; }
    Underline > .underline--bar { color: #f2a0cc; background: #211a28; }
    #status { height: 1; padding: 0 3; color: #aaa0b2; }
    #brief-actions { display: none; height: 3; padding: 0 2; }
    #brief-actions Button { width: auto; min-width: 8; height: 3; border: none;
        padding: 0 2; margin-right: 1; background: #55344e; color: #eee8f1; }
    #brief-hint { height: 3; width: 1fr; padding: 1 1; color: #aaa0b2; }
    #result-actions { display: none; height: 1; padding: 0 2; }
    #result-actions Button { width: auto; min-width: 8; height: 1; padding: 0 1;
        border: none; background: #2e2435; color: #f2a0cc; margin-right: 1; }
    #result-actions #result-summary { width: 1fr; height: 1; padding: 0 1 0 0; color: #c9bdd2; }
    #composer { height: auto; margin: 0 2; }
    #prompt { height: 3; border: round #654968; background: #241d2c;
        padding: 0 1; scrollbar-size: 1 1; }
    #prompt:focus { border: round #f2a0cc; }
    #composer-actions { height: 1; align-vertical: middle; }
    #prompt-meta { width: 1fr; height: 1; color: #aaa0b2; padding-left: 1; }
    #guided-picker, #expand-prompt, #mode-picker, #jev-picker { height: 1; width: auto; min-width: 5; border: none;
        padding: 0 1; background: #2e2435; color: #c9bdd2; margin-right: 1; }
    #send-prompt, #stop-run { width: 18; min-width: 14; height: 1;
        background: #55344e; color: #eee8f1; border: none; }
    #stop-run { display: none; color: #ee9b9b; }
    #send-prompt:hover { background: #72445f; }
    Screen.input-expanded #body, Screen.input-expanded #status, Screen.input-expanded #brief-actions { display: none; }
    Screen.input-expanded #composer { height: 1fr; }
    Footer { background: #201a27; color: #aaa0b2; }
    FooterKey { background: #201a27; }
    FooterKey .footer-key--key { background: #32243b; color: #f2a0cc; }
    FooterKey .footer-key--description { background: #201a27; color: #aaa0b2; }
    Screen.narrow #body { padding: 0 1; }
    Screen.narrow #rail { width: 1fr; margin-left: 0; border-left: none; }
    Screen.narrow.details-open #main { display: none; }
    Screen.short #masthead { height: 2; border-bottom: none; }
    Screen.short #phase-strip { margin-top: 0; }
    Screen.short #composer { margin: 0 1; }
    Screen.short #welcome { padding: 1; }
    Screen.short #navigation { padding: 0 1; }
    Screen.short #navigation Button { padding: 0 1; margin-right: 0; }
    Screen.short #prompt-meta { width: 1fr; }
    Screen.short #guided-picker, Screen.short #mode-picker, Screen.short #jev-picker { display: none; }
    Screen.narrow #rail { display: none; }
    Screen.narrow #result-summary { display: none; }
    """

    def __init__(self, session: Any, initial_prompt: Optional[str] = None,
                 replay_events: Optional[list] = None, guided=None, intake=None) -> None:
        super().__init__()
        self.session = session
        self.initial_prompt = initial_prompt
        self.replay_events = replay_events
        self.is_replay = replay_events is not None
        self.guided = bool(hasattr(session, "runner") if guided is None else guided)
        self.intake = intake
        if self.guided and not self.is_replay and self.intake is None:
            from .intake import IntakeController
            self.intake = IntakeController(session)
        self._preparing = False
        self._brief_revisions_seen = set()
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
        self._last_worker_card = None
        self._last_answer = ""
        self._answer_card = None
        self._activity = None
        self._activity_groups = []
        self._expanded_input = False
        self._seen_sequences = set()
        self._runner = None
        self._view = None
        self._clock = None

    def compose(self) -> ComposeResult:
        yield Static(id="masthead")
        with Horizontal(id="navigation"):
            yield Button("＋ New", id="nav-new")
            yield Button("Task", id="nav-brief")
            yield Button("Sessions", id="nav-sessions")
            yield Button("Files", id="nav-files")
            yield Button("JEVIS", id="nav-jev")
            yield Button("Logs", id="nav-logs")
            yield Button("Menu", id="nav-menu")
        with Horizontal(id="body"):
            with Vertical(id="main"):
                yield Static(id="phase-strip")
                with VerticalScroll(id="chat"):
                    yield Static(Text(
                        "JEVIS: an agent that works from the terminal\n\n"
                        "1  Describe your idea in plain words.\n"
                        "2  JEVIS asks up to three linked questions per round while the result is unclear.\n"
                        "3  Check the goal, the files and the criteria in the plan.\n"
                        "4  Press “Start work”: Codex changes the project, JEVIS shows decisions and checks.\n\n"
                        "Discussion → plan → execution is on by default.\n"
                        "If the plan is already written, pick “Straight to the task” below.\n\n"
                        "Enter  send   Ctrl+J  new line   ⌘⌫ or Ctrl+U  delete line\n"
                        "F3  logs   F5  questions and plan   F6  JEVIS decisions", style=MUTED), id="welcome")
                    yield Button("Insert an example task", id="welcome-example")
            with Vertical(id="rail"):
                yield Static("JEVIS · LIVE LOGS", id="drawer-title")
                yield Static("Phases and commands appear here as they happen", id="live-log-help")
                with TabbedContent(initial="events-tab", id="details-tabs"):
                    with TabPane("Jev", id="decision-tab"):
                        with VerticalScroll(classes="detail-scroll"):
                            yield Static(id="graph")
                            yield Static(id="decisions")
                    with TabPane("Checks", id="evidence-tab"):
                        with VerticalScroll(classes="detail-scroll"):
                            yield Static(id="evidence")
                    with TabPane("Events", id="events-tab"):
                        yield RichLog(id="event-log", markup=False, highlight=False,
                                      wrap=True, min_width=20, max_lines=4000)
        with Horizontal(id="brief-actions"):
            yield Button("Clarify the task", id="brief-open")
            yield Static(id="brief-hint")
        with Horizontal(id="result-actions"):
            yield Static(id="result-summary")
            yield Button("↓ Answer", id="result-answer")
            yield Button("Files", id="result-files")
            yield Button("Copy", id="result-copy")
            yield Button("Export", id="result-export")
        yield Static(id="status")
        with Vertical(id="composer"):
            yield PromptEditor(id="prompt", soft_wrap=True, tab_behavior="focus")
            with Horizontal(id="composer-actions"):
                yield Static(id="prompt-meta")
                yield Button("Discuss ▾", id="guided-picker")
                yield Button("Execute ▾", id="mode-picker")
                yield Button("Jev ▾", id="jev-picker")
                yield Button("↕", id="expand-prompt")
                yield Button("Send ↵", id="send-prompt")
                yield Button("■ Stop", id="stop-run")
        yield Footer()

    def on_mount(self) -> None:
        self._view = self.screen
        self._responsive(self.size.width, self.size.height)
        self._details(not self._view.has_class("narrow"), "events-tab")
        self._clock = self.set_interval(0.25, self._refresh_status)
        self._restore_history()
        editor = self._view.query_one("#prompt", PromptEditor)
        editor.border_title = " Your message "
        editor.focus()
        if not self.is_replay:
            from .catalog import load_draft
            editor.load_text(self.initial_prompt if self.initial_prompt is not None else load_draft(self.session))
        self.call_after_refresh(self._resize_prompt)
        if self.intake and self.intake.state.get("last_error"):
            self._chat("ERROR", self.intake.state["last_error"], YELLOW, activity=False)
        if self.intake and self.intake.state.get("status") in {"questions", "plan"}:
            self.call_after_refresh(self.action_open_brief)

    def _restore_history(self) -> None:
        self._restoring = True
        prior = self.replay_events if self.is_replay else self.session.events()
        for event in prior or []:
            self._receive(event)
        if self.is_replay:
            self.notify("Viewing saved events · no tools are run", timeout=3)
        elif prior:
            self.notify("History restored. You can continue the conversation.", timeout=3)
        self._restoring = False
        self._refresh_all()
        self.run_worker(self._settle_history(), group="restore-view", exclusive=True, exit_on_error=False)

    async def _settle_history(self):
        for group in tuple(self._activity_groups):
            await group.settled.wait()
        if self._ui_active():
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

    def _chat(self, role: str, text: Any, color: str = CREAM, activity: Optional[bool] = None):
        if not self._ui_active():
            return
        original = role
        role = {"SYSTEM": "SYSTEM", "YOU": "YOU", "PLAN": "PLAN",
                "CHECKS": "CHECKS", "ERROR": "ERROR", "WORKER": "WORKER",
                "ASSISTANT": "WORKER", "SESSION STATUS": "SESSION", "LATEST JEV": "LATEST JEV",
                "SCREENSHOT SAVED": "SCREENSHOT SAVED", "REPLAY": "REPLAY"}.get(role, role)
        self._hide_welcome()
        kind = "user" if original == "YOU" else "jev" if original == "JEV" else "message" if original in ("WORKER", "ASSISTANT") else "notice"
        card = ConversationCard(role, plain(text), color, markdown=original in ("WORKER", "ASSISTANT"), kind=kind)
        chat = self._view.query_one("#chat", VerticalScroll)
        follow = chat.is_vertical_scroll_end or original == "YOU"
        if activity is None:
            activity = original in {"JEV", "CHECKS", "PLAN", "CONTEXT", "CHECK TRIAGE", "MODE", "POLICY", "WORKER", "ASSISTANT"}
        if activity:
            self._ensure_activity().add(card)
        else:
            chat.mount(card)
        if not self._restoring and follow:
            self.call_after_refresh(self._scroll_chat)
        return card

    def _ensure_activity(self):
        if self._activity is None:
            self._activity = ActivityGroup()
            self._activity_groups.append(self._activity)
            self._view.query_one("#chat", VerticalScroll).mount(self._activity)
        return self._activity

    def _hide_welcome(self) -> None:
        for widget in self._view.query("#welcome, #welcome-example"):
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
            group = self._ensure_activity()
            group.add(self._tools[key])
            group.tool_count += 1
            group.update_summary()
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
            self._last_worker_card = None
            self._last_answer = ""
            self._answer_card = None
            self._activity = None
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
            brief = plain(data.get("purpose", "Structured decision"), 200)
            for qid, answer in (data.get("answers") or {}).items():
                if isinstance(answer, dict):
                    value = answer.get("choice", answer.get("noul", answer.get("score", "—")))
                    brief += "\n{} → {}".format(qid, value)
                    if answer.get("confidence") is not None:
                        brief += " · confidence {:.2f}".format(number(answer["confidence"]))
            if data.get("applied") is False:
                brief += "\nObservation · the decision is not applied"
            self._chat("JEV", brief, AMBER)
            self._activity.jev_count += 1
            self._activity.update_summary()
        elif kind == "tool":
            self._tool(event, data)
        elif kind == "context":
            self._source_context = data
            paths = data.get("selected") or []
            brief = "{} fragments · {} · {} files scanned".format(
                len(paths), data.get("selection", "context"), data.get("files_scanned", "?"))
            if paths:
                brief += "\n" + ", ".join(plain(item, 140) for item in paths[:8])
            if data.get("partial"):
                brief += " · selection truncated"
            self._chat("CONTEXT", brief, MUTED)
        elif kind == "triage":
            self._chat("CHECK TRIAGE", data.get("summary") or data, YELLOW)
        elif kind == "policy":
            self._chat("MODE", data.get("summary") or data.get("message") or data, MUTED)
        elif kind == "message":
            role = str(data.get("role", "worker")).upper()
            card = self._chat(role, data.get("text", ""), CREAM)
            if role in {"WORKER", "ASSISTANT"}:
                self._last_worker_text = str(data.get("text", ""))
                self._last_worker_card = card
        elif kind == "checks":
            self._checks = data
            self._chat("CHECKS", "{} / {} passed\n".format(data.get("passed", "?"), data.get("total", "?")) +
                       "\n".join(("✓ " if item.get("passed") else "× ") + str(item.get("title", item.get("id", "check")))
                                 for item in data.get("items", []) if isinstance(item, dict)), GREEN)
            self._activity.checks = data
            self._activity.update_summary()
        elif kind == "files":
            self._files = data.get("changed") or []
        elif kind == "meters":
            self._meters.update(data)
        elif kind == "brief":
            response = data.get("response") or {}
            status = data.get("status", "")
            revision = data.get("revision", 0)
            identity = (status, revision, response.get("message", ""))
            if not data.get("last_error") and status in {"questions", "plan", "answer"} and identity not in self._brief_revisions_seen:
                self._brief_revisions_seen.add(identity)
                if self._activity:
                    self._activity.update_summary(finished=True, status="complete")
                if status == "answer":
                    self._last_answer = response.get("answer") or response.get("message", "")
                    self._answer_card = self._chat("ASSISTANT", self._last_answer, AMBER, activity=False)
                    if self._answer_card:
                        self._answer_card.add_class("answer")
                    self._outcome = "answered"
                elif status == "questions":
                    self._chat("QUESTIONS", response.get("message") or "A few details need clarifying.", AMBER, activity=False)
                    self._outcome = "needs_input"
                else:
                    plan = response.get("plan") or {}
                    self._chat("PLAN READY", plan.get("title", "") + "\n" + plan.get("goal", ""), AMBER, activity=False)
                    self._outcome = "plan_ready"
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
            if summary and summary == self._last_worker_text and self._last_worker_card and self._activity:
                self._activity.discard(self._last_worker_card)
            if self._acceptance_scope:
                self._chat("ACCEPTANCE SCOPE", self._acceptance_scope, MUTED, activity=True)
            if self._activity:
                self._activity.update_summary(finished=True, status=self._outcome)
            self._last_answer = str(summary or self._last_worker_text or self._detail or "Turn finished.")
            self._answer_card = self._chat("ASSISTANT", self._last_answer, AMBER, activity=False)
            if self._answer_card:
                self._answer_card.add_class("answer")
        elif kind == "error":
            self._outcome = "error"
            for card in self._tools.values():
                if not card.is_terminal:
                    card.update_event({"status": "stopped"})
            self._chat("ERROR", data.get("message", "Unknown error"), YELLOW)
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
            graph.append("○  Waiting for a task\n", style=MUTED)
            graph.append("   Real phases will appear here.", style=MUTED)
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
            graph.append("Plan · intended steps\n", style=MUTED)
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
            ribbon.append("○  Ready for a task   ·   actions appear once you send", style=MUTED)
        if self.guided:
            state = self.intake.state.get("status", "idle") if self.intake else "idle"
            if self._preparing:
                label = "● Clarifying the task  →  Plan  →  Execution"
            elif state == "questions":
                label = "● Your answers  →  Plan  →  Execution"
            elif state == "plan":
                label = "✓ Task is clear  →  ● Agreeing the plan  →  Execution"
            elif self._busy:
                label = "✓ Plan accepted  →  ● Execution  →  Checks"
            else:
                label = ""
            ribbon = Text(label, style=AMBER)
        strip = self._view.query_one("#phase-strip", Static)
        strip.display = bool(ribbon.plain.strip()) and (self._busy or bool(self.intake and self.intake.state.get("status") in {"questions", "plan"}))
        strip.update(ribbon)

    def _render_decisions(self) -> None:
        data = self._latest_jev
        out = Text()
        if not data:
            out.append("No Jev answer yet.\n\n", style=MUTED)
            out.append("Choice → picks an option\nScore  → a level on a scale\nNoul   → how far a statement holds", style=MUTED)
        else:
            out.append(plain(data.get("purpose", "Decision"), 300) + "\n", style=f"bold {CREAM}")
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
                        out.append("░" * (width - filled), style="#49364f")
                        out.append(" {:5.1f}%\n".format(p * 100), style=MUTED)
            out.append("\nConfidence is a field of the answer; the bars show the distribution.", style=MUTED)
        self._view.query_one("#decisions", Static).update(out)

    def _render_evidence(self) -> None:
        out = Text()
        if self._meters:
            out.append("Calls and usage\n", style=f"bold {AMBER}")
            out.append("Jev {} · worker {} · planning {}\n".format(
                self._meters.get("jev_calls", 0), self._meters.get("worker_calls", 0),
                self._meters.get("planner_calls", 0)), style=CREAM)
            out.append("{} events · {:.1f} s\n".format(self._event_count, self._elapsed_ms / 1000), style=MUTED)
            if self._meters.get("usage_complete") is False:
                out.append("usage incomplete\n", style=YELLOW)
            out.append("\n")
        if self._checks:
            out.append("{} / {} checks passed\n".format(self._checks.get("passed", "?"), self._checks.get("total", "?")),
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
            out.append("No checks have run yet.\n", style=MUTED)
        if self._acceptance_scope:
            out.append("\nAcceptance scope\n", style=f"bold {YELLOW}")
            out.append(self._acceptance_scope + "\n", style=YELLOW)
        out.append("\nChanged files\n", style=f"bold {AMBER}")
        if self._files:
            for filename in self._files[:30]:
                out.append("  " + plain(filename, 180) + "\n", style=CREAM)
            if len(self._files) > 30:
                out.append("  +{} more in the log\n".format(len(self._files) - 30), style=MUTED)
        else:
            out.append("  No changes yet.\n", style=MUTED)
        out.append("\nArtifacts\n", style=f"bold {AMBER}")
        out.append(str(self.session.directory), style=MUTED)
        self._view.query_one("#evidence", Static).update(out)

    def _refresh_status(self) -> None:
        if not self._ui_active():
            return
        elapsed = self._elapsed_ms / 1000
        if self._busy and self._turn_started is not None:
            elapsed = max(elapsed, time.monotonic() - self._turn_started)
        mode = "Replay" if self.is_replay else "Reading the task" if self._preparing else "Working" if self._busy else "Ready for a message"
        execution_mode = getattr(self.session, "execution_mode", "auto")
        jev_mode = getattr(self.session, "jev_mode", "assist")
        top = Text("JEVIS", style=f"bold {AMBER}")
        top.append(" / HARNESS", style=f"bold {CREAM}")
        top.append("   ·   " + mode, style=MUTED)
        if self.guided:
            top.append("   ·   with task clarification", style=MUTED)
        if self.size.height >= 28:
            path = str(self.session.workspace)
            if len(path) > self.size.width - 8:
                path = "…/" + "/".join(Path(path).parts[-3:])
            top.append("\n" + plain(path, 180), style=MUTED)
        self._view.query_one("#masthead", Static).update(top)
        status = Text("● " if self._busy else "○ ", style=AMBER if self._busy else MUTED)
        status.append("{:5.1f}s  ".format(elapsed), style=CREAM)
        if self._meters.get("usage_complete") is False:
            status.append("usage incomplete · ", style=f"bold {YELLOW}")
        status.append("Reading the request and the project" if self._preparing else plain(self._detail, 100), style=MUTED)
        self._view.query_one("#status", Static).update(status)
        self._view.query_one("#status").display = self._busy and not self._expanded_input
        active = self._busy or self.session.busy
        self._view.query_one("#stop-run").display = active
        self._view.query_one("#send-prompt").display = not active
        for name in ("nav-new", "nav-sessions", "mode-picker", "jev-picker"):
            self._view.query_one("#" + name, Button).disabled = active or self.is_replay
        self._view.query_one("#mode-picker", Button).label = "Plan ▾" if execution_mode == "plan" else "Execute ▾"
        self._view.query_one("#jev-picker", Button).label = {"assist": "Jev: assist ▾", "observe": "Jev: observe ▾", "off": "Jev: off ▾"}.get(jev_mode, "Jev ▾")
        self._view.query_one("#guided-picker", Button).label = "Discuss ▾" if self.guided else "Straight to the task ▾"
        self._view.query_one("#result-actions").display = bool(self._last_answer) and not active and not self._expanded_input
        brief = status_label(self._outcome)
        if self._files:
            brief += " · files: {}".format(len(self._files))
        self._view.query_one("#result-summary", Static).update(Text(brief, style=GREEN))
        state = self.intake.state if self.intake else {}
        pending = self.guided and state.get("status") in {"questions", "plan", "interrupted"}
        self._view.query_one("#brief-actions").display = bool(pending and not active and not self._expanded_input)
        self._view.query_one("#brief-open", Button).label = "View the plan" if state.get("status") == "plan" else "Answer the questions" if state.get("status") == "questions" else "Continue the discussion"
        self._view.query_one("#brief-hint", Static).update("Work starts once the plan is accepted" if state.get("status") == "plan" else "Pick an option or write in your own words")
        self._view.query_one("#nav-brief", Button).disabled = active or self.is_replay
        self._view.query_one("#nav-brief").display = self.guided
        self._view.query_one("#send-prompt", Button).label = "Clarify ↵" if pending else "Discuss ↵" if self.guided else "Send ↵"

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
                self.notify("Draft not saved to disk · limit 20,000 characters", severity="warning")

    def _resize_prompt(self) -> None:
        if not self._ui_active():
            return
        editor = self._view.query_one("#prompt", PromptEditor)
        rows = max(1, editor.wrapped_document.height)
        editor.styles.height = "1fr" if self._expanded_input else min(
            max(3, rows + 2), max(5, self.size.height // 2 - 3))
        lines = len(editor.text.split("\n")) if editor.text else 0
        self._view.query_one("#prompt-meta", Static).update(
            "{} lines · {} chars · Ctrl+J ↵".format(lines, len(editor.text)))

    def action_expand_input(self) -> None:
        if not self._ui_active() or self.screen is not self._view:
            return
        self._expanded_input = not self._expanded_input
        self._view.set_class(self._expanded_input, "input-expanded")
        self._resize_prompt()
        self._view.query_one("#prompt", PromptEditor).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {"send-prompt": self.action_submit_prompt, "stop-run": self._stop,
                   "nav-sessions": self.action_sessions, "nav-files": self.action_files,
                   "nav-jev": self.action_toggle_details, "nav-logs": self.action_toggle_events,
                   "nav-menu": self.action_palette, "welcome-example": self.action_example,
                   "expand-prompt": self.action_expand_input, "guided-picker": self.action_guided_picker,
                   "mode-picker": self.action_mode_picker,
                   "jev-picker": self.action_jev_picker, "result-answer": self.action_latest_answer,
                   "result-files": self.action_files, "result-copy": self.action_copy_answer,
                   "result-export": self.action_export, "nav-brief": self.action_open_brief,
                   "brief-open": self.action_open_brief}
        if event.button.id in actions:
            event.stop()
            actions[event.button.id]()
        elif event.button.id == "nav-new":
            event.stop()
            self.run_worker(self.action_new_session(), exclusive=True, group="navigation")

    def on_prompt_editor_submitted(self, event: PromptEditor.Submitted) -> None:
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
            self.notify("The message is longer than 20,000 characters. Shorten it; the text stays in the editor.", severity="warning")
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
                self._chat("LATEST JEV", self._latest_jev or "No answer yet", AMBER)
            elif command in ("/details", "/events"):
                self.action_toggle_events() if command == "/events" else self.action_toggle_details()
            elif command == "/sessions":
                self.action_sessions()
            elif command == "/new":
                self.run_worker(self.action_new_session(), exclusive=True, group="navigation")
            elif command in ("/brief", "/plan"):
                self.action_open_brief()
            elif command in ("/guided", "/direct"):
                self._set_guided(command == "/guided")
            elif command == "/files":
                self.action_files()
            elif command == "/export":
                self.action_export()
            elif command in ("/mode", "/jev", "/worker", "/web"):
                parts = prompt.split()
                field = {"/mode": "execution_mode", "/jev": "jev_mode",
                         "/worker": "worker", "/web": "web"}[command]
                if len(parts) == 2:
                    self._configure(field, parts[1])
                else:
                    self._chat("SYSTEM", "/mode auto|plan   /jev assist|observe|off   /worker codex|claude   /web on|off", MUTED)
            elif command == "/stop":
                self._stop()
            elif command == "/clear":
                self._view.query_one("#chat", VerticalScroll).remove_children()
                self._tools = {}
                self._activity, self._activity_groups = None, []
                self._answer_card = None
                self._view.query_one("#event-log", RichLog).clear()
                self._chat("SYSTEM", "Screen cleared. The events are kept on disk.", MUTED)
            elif command == "/bottom":
                self._scroll_chat()
            elif command in ("/quit", "/exit"):
                if self._busy:
                    self._stop()
                    self._chat("SYSTEM", "Stopping. Repeat /quit once the task has finished.", MUTED)
                else:
                    self._persist_draft()
                    self.exit()
            else:
                self._chat("SYSTEM", "Unknown command. See /help for the list.", YELLOW)
            return
        if self.is_replay:
            self._chat("REPLAY", "This is a replay. Start a normal session for new work.", YELLOW)
            return
        if self._busy or self.session.busy:
            self._view.query_one("#prompt", PromptEditor).load_text(prompt)
            self._chat("SYSTEM", "The task is running. The next message is kept in the editor; /stop to stop it.", YELLOW)
            return
        if self.guided and self.intake:
            self._start_intake(prompt)
            return
        self._busy = True
        self._outcome = "running"
        self._turn_started = time.monotonic()
        self._elapsed_ms = 0
        self._refresh_status()
        self._runner = self.run_worker(self._run_turn(prompt), name="agent-turn", exclusive=True,
                                       exit_on_error=False)

    def _set_guided(self, enabled):
        if self._busy or self.session.busy or self.is_replay:
            self.notify("The discussion mode changes between turns", severity="warning")
            return
        self.guided = bool(enabled)
        if enabled and self.intake is None:
            from .intake import IntakeController
            self.intake = IntakeController(self.session)
        self.notify("We clarify the task and agree the plan first" if enabled else "Next requests go straight to execution")
        self._refresh_all()

    def _start_intake(self, text, answers=None):
        if self.is_replay or self._busy or self.session.busy or not self.intake:
            return
        self._busy = self._preparing = True
        self._outcome = "running"
        self._turn_started = time.monotonic()
        self._elapsed_ms = 0
        self._refresh_all()
        self._runner = self.run_worker(self._prepare_brief(text, answers), name="prepare-task", exclusive=True,
                                       group="agent-turn", exit_on_error=False)

    async def _prepare_brief(self, text, answers):
        try:
            state = await self.intake.prepare(text, self.emit, answers=answers)
            if state.get("last_error"):
                self._chat("ERROR", state["last_error"], YELLOW, activity=False)
        except Exception as exc:
            self._chat("ERROR", plain(str(exc), 2000), YELLOW, activity=False)
        finally:
            self._busy = self._preparing = False
            self._refresh_all()
            if self._ui_active():
                # Drain the queued final event before opening its interactive view.
                if not self.intake.state.get("last_error"):
                    self.call_after_refresh(self.action_open_brief)
                else:
                    self._focus_editor()

    def action_open_brief(self):
        if self.screen is not self._view or self.is_replay or self._busy or self.session.busy:
            return
        if not self.intake:
            self._set_guided(True)
        state = self.intake.state
        response = state.get("response") or {}
        from .intake_widgets import QuestionsScreen, PlanScreen
        if state.get("status") == "questions":
            self.push_screen(QuestionsScreen(response.get("questions") or [],
                                             draft_answers=state.get("draft_answers"),
                                             on_draft=self.intake.save_draft_answers), self._answers_selected)
        elif state.get("status") == "plan":
            revision = state.get("revision")
            notice = state.get("last_error") or ("Execution is off in “Plan only” mode. Close the plan and pick “Execute”." if self.session.execution_mode == "plan" else "")
            self.push_screen(PlanScreen(response.get("plan") or {},
                                        original_request=state.get("original", ""),
                                        refined_prompt=state.get("refined_prompt", ""),
                                        can_execute=not bool(notice), notice=notice),
                             lambda choice: self._plan_selected(choice, revision))
        else:
            if state.get("status") == "interrupted":
                self.notify("The discussion was interrupted. Say what to continue or change.")
            self._focus_editor()

    def _answers_selected(self, answers):
        self._focus_editor()
        if answers is not None:
            self._start_intake("", answers=answers)

    def _plan_selected(self, choice, revision):
        self._focus_editor()
        if not isinstance(choice, dict):
            return
        if choice.get("action") == "revise" and choice.get("feedback", "").strip():
            self._start_intake(choice["feedback"])
        elif choice.get("action") == "execute":
            if self._busy or self.session.busy:
                return
            self._busy = True
            self._outcome = "running"
            self._turn_started = time.monotonic()
            self._refresh_all()
            self._runner = self.run_worker(self._execute_brief(revision), name="approved-task",
                                           exclusive=True, group="agent-turn", exit_on_error=False)

    async def _execute_brief(self, revision):
        try:
            await self.intake.execute(revision, self.emit)
        except Exception as exc:
            self._chat("ERROR", plain(str(exc), 2000), YELLOW, activity=False)
        finally:
            self._busy = False
            self._refresh_all()
            self._focus_editor()

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
            self._detail = "Stop requested; waiting for the running process to finish."
            self._chat("SYSTEM", self._detail, YELLOW)
        else:
            self._chat("SYSTEM", "No task is running right now.", MUTED)

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

    def action_focus_prompt(self) -> None:
        if self.screen is self._view:
            self._details(False)
            self._focus_editor()

    def action_back_to_chat(self) -> None:
        if self.screen is self._view:
            if self._expanded_input:
                self.action_expand_input()
            self.action_focus_prompt()

    def action_chat_page(self, direction: int) -> None:
        if self.screen is self._view:
            chat = self._view.query_one("#chat", VerticalScroll)
            chat.scroll_relative(y=direction * max(3, chat.size.height - 2), animate=False)

    def action_toggle_activity(self) -> None:
        if self.screen is self._view and self._activity:
            self._activity.collapsed = not self._activity.collapsed
            self._view.query_one("#chat", VerticalScroll).scroll_to_widget(self._activity, animate=False)

    def action_latest_answer(self) -> None:
        if self.screen is self._view:
            self._details(False)
            self._scroll_chat()

    def action_copy_answer(self) -> None:
        if self._last_answer:
            fallback = Path(self.session.directory) / "exports" / "answer.txt"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            fallback.write_text(self._last_answer, encoding="utf-8")
            clipboard_error = None
            try:
                self.copy_to_clipboard(self._last_answer)
            except Exception as exc:  # clipboard support depends on the terminal
                clipboard_error = exc
            if clipboard_error:
                self.notify("The terminal clipboard is unavailable. Full answer saved: {}".format(fallback), timeout=6)
            else:
                self.notify("Answer copied; the full text is also saved: {}".format(fallback), timeout=5)

    def action_mode_picker(self) -> None:
        self.push_screen(PickerScreen("What the agent may do", [
            {"title": "Execute", "description": "Read, change files and run checks", "value": "/mode auto"},
            {"title": "Plan only", "description": "Study the project without changing files", "value": "/mode plan"},
        ]), self._palette_selected)

    def action_guided_picker(self) -> None:
        """Choose the conversation gate independently from file permissions."""
        self.push_screen(PickerScreen("How to start the task", [
            {"title": "Discussion and plan", "description": "Recommended · questions, then explicit plan acceptance", "value": "/guided"},
            {"title": "Straight to the task", "description": "Plan already written · next request goes to the worker", "value": "/direct"},
        ]), self._palette_selected)

    def action_jev_picker(self) -> None:
        self.push_screen(PickerScreen("Jev's role", [
            {"title": "Assists", "description": "Jev decisions affect the work", "value": "/jev assist"},
            {"title": "Observes", "description": "Decisions are shown but not applied", "value": "/jev observe"},
            {"title": "Off", "description": "Work without TypeSafe calls", "value": "/jev off"},
        ]), self._palette_selected)

    async def action_new_session(self) -> None:
        if self.screen is not self._view or self._busy or self.session.busy or self.is_replay:
            return
        from .core import Session
        self._persist_draft()
        try:
            fresh = Session.create(Path(self.session.directory).parent)
        except (OSError, ValueError) as exc:
            self.notify(str(exc), severity="error")
            return
        await self._session_selected(str(fresh.directory))

    def _details(self, show: bool, tab: Optional[str] = None) -> None:
        self._show_details = show
        narrow = self._view.has_class("narrow")
        # Wide terminals keep a compact live-log rail mounted all the time.
        # In a narrow terminal it becomes an on-demand drawer so the editor
        # remains usable.
        self._view.query_one("#rail").display = show if narrow else True
        self._view.set_class(show and narrow, "details-open")
        if tab:
            self._view.query_one("#details-tabs", TabbedContent).active = tab
        self._show_events = show and self._view.query_one("#details-tabs", TabbedContent).active == "events-tab"

    def action_toggle_details(self) -> None:
        if self.screen is self._view:
            self._details(not self._show_details if self._view.has_class("narrow") else True, "decision-tab")

    def action_toggle_events(self) -> None:
        if self.screen is self._view:
            active = self._view.query_one("#details-tabs", TabbedContent).active
            show = not (self._show_details and active == "events-tab") if self._view.has_class("narrow") else True
            self._details(show, "events-tab")

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
            {"title": "New chat", "description": "Ctrl+N · a new working folder; the current session is kept", "value": "/new"},
            {"title": "Task questions and plan", "description": "F5 · keep answering or revise the plan", "value": "/brief"},
            {"title": "Discuss the task first", "description": "/guided · questions and a plan before work", "value": "/guided"},
            {"title": "Direct execution", "description": "/direct · next requests go straight to the worker", "value": "/direct"},
            {"title": "Jev details and graph", "description": "F6 · probabilities, checks and files", "value": "/details"},
            {"title": "Event log", "description": "F3 · the exact saved data", "value": "/events"},
            {"title": "Resume a session", "description": "/sessions · search previous tasks", "value": "/sessions"},
            {"title": "Files and changes", "description": "/files · source text and diff", "value": "/files"},
            {"title": "Export the conversation", "description": "/export · Markdown in the session folder", "value": "/export"},
            {"title": "Mode: plan", "description": "/mode plan · read only", "value": "/mode plan"},
            {"title": "Mode: execute", "description": "/mode auto · works with files", "value": "/mode auto"},
            {"title": "Jev: assist", "description": "/jev assist · apply decisions", "value": "/jev assist"},
            {"title": "Jev: observe", "description": "/jev observe · judge without steering", "value": "/jev observe"},
            {"title": "Jev: off", "description": "/jev off · no Jev calls", "value": "/jev off"},
            {"title": "Worker: Codex", "description": "/worker codex · OS sandbox, network off", "value": "/worker codex"},
            {"title": "Worker: Claude", "description": "/worker claude · no Bash, edits only in the working folder", "value": "/worker claude"},
            {"title": "Web: on", "description": "/web on · search and read pages; pages are data, not commands", "value": "/web on"},
            {"title": "Web: off", "description": "/web off · work only from local files", "value": "/web off"},
            {"title": "Example task", "description": "F2 · insert, do not run", "value": "/example"},
            {"title": "Help and keyboard shortcuts", "description": "/help", "value": "/help"},
            {"title": "Session status", "description": "/status", "value": "/status"},
        ]
        self.push_screen(PickerScreen("Commands", choices), self._palette_selected)

    def _palette_selected(self, value: Optional[str]) -> None:
        self._focus_editor()
        if value:
            self._submit(value)

    def _configure(self, name: str, value: str) -> None:
        if self.is_replay or self._busy or self.session.busy:
            self._chat("SYSTEM", "The mode changes only in a live session, once the task has finished.", YELLOW)
            return
        try:
            if name == "worker":
                self.session.use_worker(value)
            elif name == "web":
                self.session.configure(web=value)
            else:
                self.session.configure(**{name: value})
        except (ValueError, RuntimeError) as exc:
            self._chat("ERROR", str(exc), YELLOW)
            return
        titles = {"execution_mode": "Execution", "jev_mode": "Jev",
                  "worker": "Worker", "web": "Web"}
        self._chat("MODE", "{} → {}".format(titles[name], value), AMBER)
        self._refresh_status()

    def action_sessions(self) -> None:
        if self.is_replay or self._busy or self.session.busy:
            self._chat("SYSTEM", "You can switch sessions once the current task has finished.", YELLOW)
            return
        from .catalog import list_sessions
        choices = [{"title": item["title"],
                    "description": "{} · {} · {} turns".format(item["id"], item.get("status", ""), item.get("turns", 0)),
                    "value": item["directory"]} for item in list_sessions(Path(self.session.directory).parent)]
        self.push_screen(PickerScreen("Sessions", choices, "Find a task…"), self._session_selected)

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
            restored_draft = load_draft(replacement)
        except (OSError, ValueError, KeyError) as exc:
            self._chat("ERROR", "Could not open the session: " + str(exc), YELLOW)
            return
        if self._draft_timer is not None:
            self._draft_timer.stop()
            self._draft_timer = None
        self.session = replacement
        if self.guided:
            from .intake import IntakeController
            self.intake = IntakeController(replacement)
        else:
            self.intake = None
        self._brief_revisions_seen.clear()
        # Keep the editor and its owner consistent before any yielding UI work;
        # a pending autosave must never write session A's draft into session B.
        self._latest_draft = restored_draft
        self._view.query_one("#prompt", PromptEditor).load_text(restored_draft)
        self._seen_sequences.clear()
        self._event_count = 0
        self._event_types = []
        self._tools = {}
        self._activity, self._activity_groups = None, []
        self._last_answer, self._last_worker_card, self._answer_card = "", None, None
        self._phases, self._latest_jev, self._checks, self._meters = {}, {}, {}, {}
        self._source_context = {}
        self._steps, self._files = [], []
        self._acceptance_scope, self._detail = "", ""
        self._outcome, self._elapsed_ms, self._turn_started = "idle", 0.0, None
        self._last_worker_text = ""
        await self._view.query_one("#chat", VerticalScroll).remove_children()
        self._view.query_one("#event-log", RichLog).clear()
        self._restore_history()
        if self.intake and self.intake.state.get("last_error"):
            self._chat("ERROR", self.intake.state["last_error"], YELLOW, activity=False)
        if not self.session.events():
            await self._view.query_one("#chat", VerticalScroll).mount(
                Static(Text(
                    "JEVIS: an agent that works from the terminal\n\n"
                    "Describe the idea → answer the questions → check the plan → press “Start work”.\n"
                    "Discussion is on by default. If a plan already exists, pick “Straight to the task” below.\n"
                    "Enter sends · Ctrl+J breaks the line · ⌘⌫ or Ctrl+U deletes the line.", style=MUTED), id="welcome"),
                Button("Insert an example task", id="welcome-example"))
        self._focus_editor()
        if self.intake and self.intake.state.get("status") in {"questions", "plan"}:
            self.call_after_refresh(self.action_open_brief)

    def action_files(self) -> None:
        from .catalog import list_artifacts
        choices = [{"title": item["path"], "description": item.get("status", ""), "value": item["path"]}
                   for item in list_artifacts(self.session)]
        self.push_screen(PickerScreen("Session files", choices, "Find a file…"), self._file_selected)

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
        self.notify("Export: " + str(path), timeout=8)

    def action_save_view(self) -> None:
        directory = Path(self.session.directory) / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        filename = directory / ("terminal-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".svg")
        filename.write_text(self.export_screenshot(title="JEVIS · " + str(self.session.id)), encoding="utf-8")
        self.notify("Terminal SVG snapshot saved", timeout=3)
