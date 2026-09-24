"""Question state transitions ported from OpenCode's question.shared.ts (MIT).

Copyright (c) 2025 opencode. Source, full notice and local differences are in
vendor/opencode/. This single-choice subset always reviews answers before submit.
Rendering, model calls and persistence deliberately live outside this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List


@dataclass(frozen=True)
class QuestionState:
    request_id: str
    tab: int = 0
    answers: List[List[str]] = field(default_factory=list)
    custom: List[str] = field(default_factory=list)
    selected: int = 0
    editing: bool = False
    submitting: bool = False


def create_question_state(request_id: str) -> QuestionState:
    return QuestionState(request_id=request_id)


def question_sync(state: QuestionState, request_id: str) -> QuestionState:
    return state if state.request_id == request_id else create_question_state(request_id)


def question_confirm(request: Dict[str, Any], state: QuestionState) -> bool:
    return state.tab == len(request["questions"])


def question_info(request: Dict[str, Any], state: QuestionState) -> Dict[str, Any]:
    return request["questions"][state.tab] if 0 <= state.tab < len(request["questions"]) else {}


def question_input(state: QuestionState) -> str:
    return state.custom[state.tab] if state.tab < len(state.custom) else ""


def question_other(request: Dict[str, Any], state: QuestionState) -> bool:
    info = question_info(request, state)
    return bool(info) and state.selected == len(info.get("options", []))


def question_total(request: Dict[str, Any], state: QuestionState) -> int:
    info = question_info(request, state)
    return len(info.get("options", [])) + 1 if info else 0


def question_answers(state: QuestionState, count: int) -> List[List[str]]:
    return [list(state.answers[i]) if i < len(state.answers) else [] for i in range(count)]


def question_set_tab(state: QuestionState, tab: int) -> QuestionState:
    return replace(state, tab=max(0, tab), selected=0, editing=False)


def question_set_selected(state: QuestionState, selected: int) -> QuestionState:
    return replace(state, selected=selected)


def question_set_editing(state: QuestionState, editing: bool) -> QuestionState:
    return replace(state, editing=editing)


def question_store_custom(state: QuestionState, tab: int, text: str) -> QuestionState:
    custom = list(state.custom)
    while len(custom) <= tab:
        custom.append("")
    custom[tab] = text
    return replace(state, custom=custom)


def _store_answer(state: QuestionState, tab: int, answer: str) -> QuestionState:
    answers = question_answers(state, max(tab + 1, len(state.answers)))
    answers[tab] = [answer] if answer else []
    return replace(state, answers=answers)


def question_pick(state: QuestionState, request: Dict[str, Any], answer: str,
                  custom: bool = False) -> QuestionState:
    next_state = _store_answer(state, state.tab, answer)
    if custom:
        next_state = question_store_custom(next_state, state.tab, answer)
    # Unlike upstream's single-question shortcut, every intake reaches review.
    return question_set_tab(next_state, min(state.tab + 1, len(request["questions"])))


def question_move(state: QuestionState, request: Dict[str, Any], direction: int) -> QuestionState:
    total = question_total(request, state)
    return replace(state, selected=(state.selected + direction) % total) if total else state


def question_select(state: QuestionState, request: Dict[str, Any]) -> QuestionState:
    info = question_info(request, state)
    if not info:
        return state
    if question_other(request, state):
        return replace(state, editing=True)
    options = info.get("options", [])
    if not 0 <= state.selected < len(options):
        return state
    return question_pick(state, request, options[state.selected]["label"])


def question_save(state: QuestionState, request: Dict[str, Any]) -> QuestionState:
    value = question_input(state).strip()
    # Empty custom text never supplies an answer or advances the interview.
    return question_pick(state, request, value, custom=True) if value else state


def question_submit(request: Dict[str, Any], state: QuestionState) -> Dict[str, Any]:
    answers = question_answers(state, len(request["questions"]))
    if not question_confirm(request, state) or any(not a or not a[0].strip() for a in answers):
        raise ValueError("Answer the questions before continuing.")
    return {"requestID": request["id"], "answers": answers}


def question_reject(request: Dict[str, Any]) -> Dict[str, Any]:
    return {"requestID": request["id"]}
