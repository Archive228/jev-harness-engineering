"""Pink, keyboard-first requirement and plan screens; no tool execution."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static, TabbedContent, TabPane, TextArea

from .choice_labels import mark_recommended
from .question_state import (QuestionState, create_question_state, question_answers,
                             question_confirm, question_input, question_save,
                             question_select, question_set_selected, question_set_tab,
                             question_store_custom, question_submit)
from .ui_widgets import CREAM, MUTED, PINK, PromptEditor, plain


def _question_id(question: Dict[str, Any], index: int) -> str:
    return str(question.get("id") or question.get("qid") or "question_%d" % index)


class QuestionsScreen(ModalScreen):
    """Collect answers, retaining drafts; dismissal can never authorize execution."""

    BINDINGS = [Binding("escape", "cancel", "Later", show=False)]
    DEFAULT_CSS = """
    QuestionsScreen * { scrollbar-color: #684763; scrollbar-color-active: #f2a0cc;
        scrollbar-background: #211a28; }
    QuestionsScreen { align: center middle; background: #18151d 94%; }
    #questions-box { width: 88; max-width: 96%; height: 24; max-height: 90%;
        padding: 1 2; background: #221c29; border: round #86536f; }
    QuestionsScreen.expanded #questions-box { height: 90%; max-height: 90%; }
    #questions-heading { height: 1; color: #f2a0cc; text-style: bold; }
    #questions-progress { height: 1; color: #aaa0b2; margin-bottom: 1; }
    #questions-body { height: 1fr; scrollbar-size: 1 1; }
    #question-text { height: auto; margin-bottom: 1; color: #ede7f0; }
    #question-options { height: auto; min-height: 3; border: none; background: #221c29; padding: 0; }
    #question-options > .option-list--option { padding: 0 1; margin-bottom: 1; }
    #question-options > .option-list--option-highlighted { background: #4a2d43; color: #ede7f0; }
    #question-custom { display: none; height: 8; min-height: 5;
        border: round #86536f; background: #2c2434; }
    #question-custom:focus { border: round #f2a0cc; }
    #question-review { height: auto; display: none; }
    #questions-notice { height: auto; min-height: 1; max-height: 3; color: #aaa0b2; }
    #questions-actions { height: 3; margin-top: 1; }
    #questions-actions Button { width: auto; min-width: 8; height: 3; margin-right: 1;
        border: none; background: #32243b; color: #c9bdd2; padding: 0 1; }
    #questions-actions #question-next { background: #55344e; color: #eee8f1; }
    #questions-actions Button:focus { background: #72445f; color: #f2a0cc; }
    """

    def __init__(self, questions: List[Dict[str, Any]], draft_answers: Optional[Dict[str, str]] = None,
                 on_draft: Optional[Callable[[Dict[str, str]], None]] = None) -> None:
        super().__init__()
        if not questions or len(questions) > 3:
            raise ValueError("Intake must contain one to three questions.")
        self.questions = questions
        self.request = {"id": "intake-" + uuid4().hex, "questions": questions}
        self.on_draft = on_draft
        self.state = create_question_state(self.request["id"])
        draft = draft_answers or {}
        answers, custom = [], []
        for index, question in enumerate(questions):
            value = draft.get(_question_id(question, index), "")
            value = value if isinstance(value, str) else ""
            answers.append([value] if value.strip() else [])
            labels = [o.get("label") for o in question.get("options", [])]
            custom.append(value if value not in labels else "")
        first_missing = next((i for i, answer in enumerate(answers) if not answer), len(questions))
        self.state = QuestionState(self.request["id"], tab=first_missing, answers=answers, custom=custom)
        self._loading_editor = False
        self._dismissed = False
        self._draft_error = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="questions-box"):
            yield Static("Refine the task", id="questions-heading")
            yield Static(id="questions-progress")
            with VerticalScroll(id="questions-body"):
                yield Static(id="question-text")
                yield OptionList(id="question-options")
                yield PromptEditor(id="question-custom")
                yield Static(id="question-review")
            yield Static(id="questions-notice")
            with Horizontal(id="questions-actions"):
                yield Button("← Back", id="question-back")
                yield Button("Next →", id="question-next")
                yield Button("Later", id="question-cancel")

    def on_mount(self) -> None:
        self.query_one("#question-custom").border_title = "Your answer · Ctrl+J: new line"
        self._render_question()

    def _answers(self, include_draft: bool = True) -> Dict[str, str]:
        answers = question_answers(self.state, len(self.questions))
        result = {_question_id(question, i): answers[i][0]
                  for i, question in enumerate(self.questions) if answers[i]}
        if include_draft and self.state.editing and self.state.tab < len(self.questions):
            key = _question_id(self.questions[self.state.tab], self.state.tab)
            value = question_input(self.state)
            if value.strip():
                result[key] = value
            else:
                result.pop(key, None)
        return result

    def _persist(self) -> bool:
        answers = dict(self._answers())
        had_error = bool(self._draft_error)
        try:
            if any(len(answer) > 4000 for answer in answers.values()):
                raise ValueError("Answer too long: 4000 characters max. The text stays in the editor.")
            if self.on_draft:
                self.on_draft(answers)
        except (ValueError, OSError) as exc:
            self._draft_error = "Could not save: " + plain(str(exc), 400)
            if self.is_mounted:
                self.query_one("#questions-notice", Static).update(Text(self._draft_error))
            return False
        self._draft_error = ""
        if had_error and self.is_mounted:
            self.query_one("#questions-notice", Static).update("Draft saved. You can continue.")
        return True

    def _render_question(self) -> None:
        review = question_confirm(self.request, self.state)
        self.set_class(self.state.editing or review, "expanded")
        self.query_one("#questions-progress", Static).update(
            "Review your answers · then we plan" if review else
            "Question %d of %d · %s" % (self.state.tab + 1, len(self.questions),
                                      plain(self.questions[self.state.tab].get("header", ""), 80)))
        self.query_one("#question-back", Button).disabled = self.state.tab == 0
        self.query_one("#question-next", Button).label = "Build the plan →" if review else "Next →"
        self.query_one("#question-review").display = review
        self.query_one("#question-text").display = not review
        self.query_one("#question-options").display = not review and not self.state.editing
        self.query_one("#question-custom").display = not review and self.state.editing
        if review:
            result = Text()
            for i, question in enumerate(self.questions):
                result.append(plain(question.get("question", ""), 800) + "\n", style="bold " + CREAM)
                answer = self._answers(False).get(_question_id(question, i), "No answer chosen")
                result.append(plain(answer, 12000) + "\n\n", style=PINK)
            self.query_one("#question-review", Static).update(result)
            self.query_one("#questions-notice", Static).update("These answers go into the plan. Work has not started yet.")
            self.query_one("#question-next").focus()
        else:
            question = self.questions[self.state.tab]
            self.query_one("#question-text", Static).update(Text(plain(question.get("question", ""), 800)))
            options = self.query_one("#question-options", OptionList)
            options.clear_options()
            decorated = mark_recommended([o["label"] for o in question.get("options", [])])
            answer = self._answers(False).get(_question_id(question, self.state.tab), "")
            selected = 0
            for i, option in enumerate(question.get("options", [])):
                chosen = answer == option["label"]
                if chosen:
                    selected = i
                label = Text(("✓ " if chosen else "") + plain(decorated[i], 240), style="bold " + CREAM)
                if option.get("description"):
                    label.append("\n" + plain(option["description"], 700), style="not bold " + MUTED)
                options.add_option(label)
            options.add_option(Text("Your answer…", style=PINK))
            if answer and answer not in [o["label"] for o in question.get("options", [])]:
                selected = len(question.get("options", []))
            options.highlighted = selected
            if self.state.editing:
                editor = self.query_one("#question-custom", PromptEditor)
                self._loading_editor = True
                editor.load_text(question_input(self.state))
                self._loading_editor = False
                editor.focus()
                self.query_one("#questions-notice", Static).update("Enter: save the answer · Ctrl+J: new line")
            else:
                options.focus()
                self.query_one("#questions-notice", Static).update("↑ ↓ and Enter: choose · or write your own answer in full")
        self.query_one("#questions-body", VerticalScroll).scroll_home(animate=False)
        if self._draft_error:
            self.query_one("#questions-notice", Static).update(Text(self._draft_error))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "question-options":
            return
        event.stop()
        self.state = question_select(question_set_selected(self.state, event.option_index), self.request)
        self._persist()
        self._render_question()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "question-custom":
            event.stop()
            if not self._loading_editor and self.state.editing:
                self.state = question_store_custom(self.state, self.state.tab, event.text_area.text)
                self._persist()

    def on_prompt_editor_submitted(self, event: PromptEditor.Submitted) -> None:
        if event.editor.id == "question-custom":
            event.stop()
            self._next()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "question-cancel":
            self.action_cancel()
        elif event.button.id == "question-back":
            if not self._persist():
                return
            tab = self.state.tab
            if self.state.editing:
                self.state = question_save(self.state, self.request)
            self.state = question_set_tab(self.state, max(0, tab - 1))
            self._persist()
            self._render_question()
        elif event.button.id == "question-next":
            self._next()

    def _next(self) -> None:
        if self._dismissed:
            return
        if question_confirm(self.request, self.state):
            try:
                question_submit(self.request, self.state)
            except ValueError as exc:
                self.query_one("#questions-notice", Static).update(str(exc))
                return
            if not self._persist():
                return
            self._dismissed = True
            self.dismiss(self._answers(False))
            return
        previous = self.state.tab
        if self.state.editing:
            if not self._persist():
                return
            self.state = question_save(self.state, self.request)
        elif question_answers(self.state, len(self.questions))[previous]:
            if not self._persist():
                return
            self.state = question_set_tab(self.state, previous + 1)
        if self.state.tab == previous:
            self.query_one("#questions-notice", Static).update("Choose an option or write your own answer.")
            return
        self._persist()
        self._render_question()

    def action_cancel(self) -> None:
        if not self._dismissed:
            self._persist()
            self._dismissed = True
            self.dismiss(None)


def plan_text(plan: Dict[str, Any]) -> Text:
    result = Text()
    sections = [("goal", "Outcome"), ("deliverables", "What you get"),
                ("steps", "How we do it"), ("acceptance", "How we check"),
                ("constraints", "Constraints"), ("assumptions", "Assumptions"),
                ("out_of_scope", "Out of scope")]
    for key, title in sections:
        value = plan.get(key)
        if not value:
            continue
        result.append(title + "\n", style="bold " + PINK)
        values = value if isinstance(value, list) else [value]
        for index, item in enumerate(values):
            prefix = "%d. " % (index + 1) if key == "steps" else "• " if len(values) > 1 else ""
            result.append(prefix + plain(item, 12000) + "\n", style=CREAM)
        result.append("\n")
    return result


class PlanScreen(ModalScreen):
    """A reviewed plan, its exact execution prompt, and an explicit start action."""

    BINDINGS = [Binding("escape", "cancel", "Later", show=False)]
    DEFAULT_CSS = """
    PlanScreen * { scrollbar-color: #684763; scrollbar-color-active: #f2a0cc;
        scrollbar-background: #211a28; }
    PlanScreen { align: center middle; background: #18151d 94%; }
    #plan-box { width: 100; max-width: 96%; height: 94%; max-height: 48;
        padding: 0 2; background: #221c29; border: round #86536f; }
    #plan-heading { height: auto; max-height: 2; color: #f2a0cc; text-style: bold; }
    #plan-tabs { height: 1fr; }
    #plan-tabs TabPane { height: 1fr; padding: 0; }
    #plan-tabs Tab { color: #aaa0b2; }
    #plan-tabs Tab.-active { color: #f2a0cc; }
    #plan-tabs Tabs:focus Tab.-active { color: #f2a0cc; background: #49324c; }
    #plan-tabs Underline > .underline--bar { color: #f2a0cc; background: #4a2d43; }
    .plan-scroll { height: 1fr; scrollbar-size: 1 1; }
    .plan-text { height: auto; }
    #plan-feedback { display: none; height: 7; background: #2c2434; border: round #f2a0cc; }
    #plan-notice { height: auto; min-height: 1; max-height: 3; color: #aaa0b2; }
    #plan-actions { height: 3; margin-top: 1; }
    #plan-actions Button { width: auto; min-width: 8; height: 3; margin-right: 1;
        border: none; background: #32243b; color: #c9bdd2; padding: 0 1; }
    #plan-actions #plan-execute { background: #55344e; color: #eee8f1; }
    #plan-actions Button:focus { background: #72445f; color: #f2a0cc; }
    """

    def __init__(self, plan: Dict[str, Any], original_request: str = "", refined_prompt: str = "",
                 can_execute: bool = True, notice: str = "") -> None:
        super().__init__()
        self.plan = plan
        self.original_request = original_request
        self.refined_prompt = refined_prompt
        self.can_execute = bool(can_execute)
        self.notice = notice
        self._revising = False
        self._dismissed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="plan-box"):
            yield Static(Text(plain(self.plan.get("title") or "Task plan", 200)), id="plan-heading")
            with TabbedContent(id="plan-tabs"):
                with TabPane("Plan", id="plan-summary-tab"):
                    with VerticalScroll(classes="plan-scroll"):
                        yield Static(plan_text(self.plan), classes="plan-text", id="plan-summary")
                with TabPane("Agent request", id="plan-prompt-tab"):
                    with VerticalScroll(classes="plan-scroll"):
                        yield Static(Text(plain(self.refined_prompt or self.original_request, 30000)),
                                     classes="plan-text", id="plan-exact-prompt")
            yield PromptEditor(id="plan-feedback")
            yield Static(Text(plain(self.notice or "↑↓: read the plan · Refine: change the task", 1000)),
                         id="plan-notice")
            with Horizontal(id="plan-actions"):
                yield Button("Start work", id="plan-execute", disabled=not self.can_execute)
                yield Button("Refine", id="plan-revise")
                yield Button("Later", id="plan-cancel")

    def on_mount(self) -> None:
        self.query_one("#plan-feedback").border_title = "What to change? · Ctrl+J: new line"
        self.query_one("#plan-summary-tab .plan-scroll").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "plan-execute" and not self._revising and self.can_execute:
            self._finish({"action": "execute"})
        elif event.button.id == "plan-cancel":
            self.action_cancel()
        elif event.button.id == "plan-revise":
            if self._revising:
                self._send_revision()
            else:
                self._revising = True
                self.query_one("#plan-execute", Button).disabled = True
                self.query_one("#plan-feedback").display = True
                self.query_one("#plan-revise", Button).label = "Send refinement"
                self.query_one("#plan-notice", Static).update("Write what to change. The agent rebuilds the plan.")
                self.query_one("#plan-feedback").focus()

    def on_prompt_editor_submitted(self, event: PromptEditor.Submitted) -> None:
        if event.editor.id == "plan-feedback":
            event.stop()
            self._send_revision()

    def _send_revision(self) -> None:
        feedback = self.query_one("#plan-feedback", PromptEditor).text.strip()
        if feedback:
            self._finish({"action": "revise", "feedback": feedback})
        else:
            self.query_one("#plan-notice", Static).update("Write exactly what to change in the plan.")

    def _finish(self, value: Optional[Dict[str, str]]) -> None:
        if not self._dismissed:
            self._dismissed = True
            self.dismiss(value)

    def action_cancel(self) -> None:
        self._finish(None)
