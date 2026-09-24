"""Guided user journeys across real persistence, intake, modal UI and execution.

Only the model transport is deterministic. These tests never call an API.
"""
import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path

from textual import events
from textual.containers import VerticalScroll
from textual.widgets import Button, OptionList, Static, TabbedContent

from jev_agent.core import Session
from jev_agent.intake import IntakeController
from jev_agent.intake_widgets import PlanScreen, QuestionsScreen
from jev_agent.tui import JevApp
from jev_agent.ui_widgets import PromptEditor
from test_engine import FixtureJudge


ROUGH_REQUEST = "Хочу что-то полезное про крипту"
QUESTIONS = [
    {"id": "outcome", "header": "Outcome", "question": "Что хотите получить?",
     "options": [
         {"label": "Локальный отчёт", "description": "Сверять сделки и комиссии из файла."},
         {"label": "Explanation", "description": "Разобраться в данных без программы."}]},
    {"id": "input", "header": "Данные", "question": "Какие данные возьмём для первого запуска?",
     "options": [
         {"label": "Пример CSV", "description": "Небольшой файл с известным результатом."},
         {"label": "Мой CSV", "description": "Уже подготовленный файл сделок."}]},
]
PLAN = {
    "title": "Локальная сверка сделок", "goal": "Получать отчёт по сделкам из CSV.",
    "deliverables": ["CLI, пример CSV и инструкция запуска"],
    "steps": ["Изучить структуру данных", "Создать локальный расчёт", "Проверить пример"],
    "acceptance": ["На примере комиссия 2 USDT отражается отдельно от суммы сделки."],
    "constraints": ["Без сетевых запросов"], "assumptions": ["Сначала один формат CSV"],
    "out_of_scope": ["Совершение биржевых сделок"],
}


def question_response():
    return {"kind": "questions", "message": "Выберем полезный результат и данные.",
            "questions": copy.deepcopy(QUESTIONS), "plan": None, "answer": ""}


def plan_response(title=None):
    plan = copy.deepcopy(PLAN)
    if title:
        plan["title"] = title
    return {"kind": "plan", "message": "Подготовлен небольшой локальный инструмент.",
            "questions": [], "plan": plan, "answer": ""}


class GuidedFixtureRunner:
    """Deterministic provider boundary; actual controller and Session do the work."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.planning_calls = []
        self.execution_calls = []
        self.pause_planning = False
        self.started = asyncio.Event()

    async def run(self, prompt, workspace, directory, emit, cancel_event,
                  readonly=False, schema=None):
        if schema is not None:
            self.planning_calls.append({"prompt": prompt, "readonly": readonly, "schema": schema})
            self.started.set()
            if self.pause_planning:
                await cancel_event.wait()
                raise asyncio.CancelledError()
            if not self.responses:
                raise AssertionError("Unexpected extra planning call")
            text = json.dumps(self.responses.pop(0), ensure_ascii=False)
        else:
            self.execution_calls.append({"prompt": prompt, "readonly": readonly})
            if not readonly:
                (workspace / "result.txt").write_text("Fixture execution completed.\n", encoding="utf-8")
            text = "Результат подготовлен в result.txt."
        return {"text": text, "completed": True,
                "usage": {"input_tokens": 20, "output_tokens": 10}}


class GuidedUserJourneyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.session = Session.create(Path(self.temporary.name) / "sessions")
        self.session.judge = FixtureJudge()

    def tearDown(self):
        self.temporary.cleanup()

    def make_app(self, responses):
        self.runner = GuidedFixtureRunner(responses)
        self.session.runner = self.runner
        self.intake = IntakeController(self.session)
        return JevApp(self.session, guided=True, intake=self.intake)

    async def wait_screen(self, pilot, app, screen_type):
        for _ in range(60):
            await pilot.pause(.03)
            if isinstance(app.screen, screen_type) and not app._busy:
                return app.screen
        self.fail("Expected %s; got %s; state=%r" %
                  (screen_type.__name__, type(app.screen).__name__, self.intake.state))

    async def wait_idle(self, pilot, app):
        for _ in range(60):
            await pilot.pause(.03)
            if not app._busy and not app.session.busy:
                return
        self.fail("The guided operation never returned to idle")

    async def submit_rough_request(self, pilot, app):
        app.query_one("#prompt", PromptEditor).load_text(ROUGH_REQUEST)
        await pilot.press("enter")

    async def accept_question_defaults(self, pilot, app):
        screen = await self.wait_screen(pilot, app, QuestionsScreen)
        screen.query_one(OptionList).focus()
        await pilot.press("enter", "enter")
        self.assertEqual(self.runner.execution_calls, [])
        await pilot.click("#question-next")
        return await self.wait_screen(pilot, app, PlanScreen)

    def assert_visible(self, screen, selector, width=80, height=24):
        widget = screen.query_one(selector)
        self.assertTrue(widget.display, selector)
        self.assertGreater(widget.region.width, 0, selector)
        self.assertGreater(widget.region.height, 0, selector)
        self.assertGreaterEqual(widget.region.x, 0, selector)
        self.assertLessEqual(widget.region.right, width, selector)
        self.assertGreaterEqual(widget.region.y, 0, selector)
        self.assertLessEqual(widget.region.bottom, height, selector)

    async def test_rough_request_answers_plan_approval_executes_exact_request_once(self):
        app = self.make_app([question_response(), plan_response()])
        async with app.run_test(size=(100, 32)) as pilot:
            await self.submit_rough_request(pilot, app)
            screen = await self.wait_screen(pilot, app, QuestionsScreen)
            self.assertEqual(self.runner.execution_calls, [])
            self.assertEqual(self.session.judge.calls, [])
            self.assertEqual(self.session.history, [])
            # The pre-highlighted recommendation is not a submitted answer.
            await pilot.click("#question-next")
            self.assertEqual(screen.state.tab, 0)
            screen.query_one(OptionList).focus()
            await pilot.press("enter", "enter")
            self.assertEqual(len(self.runner.planning_calls), 1)
            await pilot.click("#question-next")
            plan_screen = await self.wait_screen(pilot, app, PlanScreen)
            compiled = self.intake.state["refined_prompt"]
            self.assertIn(ROUGH_REQUEST, compiled)
            self.assertIn("Локальный отчёт", compiled)
            self.assertIn("Пример CSV", compiled)
            self.assertIn(PLAN["acceptance"][0], compiled)
            self.assertEqual(self.runner.execution_calls, [])
            plan_screen.query_one(TabbedContent).active = "plan-prompt-tab"
            await pilot.pause()
            self.assertEqual(plan_screen.query_one("#plan-exact-prompt", Static).renderable.plain, compiled)
            await pilot.click("#plan-execute")
            await self.wait_idle(pilot, app)
            self.assertEqual(len(self.runner.execution_calls), 1)
            self.assertTrue((self.session.workspace / "result.txt").is_file())
            requests = list(self.session.directory.glob("turn-*/request.json"))
            self.assertEqual(len(requests), 1)
            self.assertEqual(json.loads(requests[0].read_text())["text"], compiled)
            self.assertEqual(self.session.history[0]["text"], compiled)
            self.assertEqual(self.intake.state["status"], "completed")
            self.assertTrue(all(call["readonly"] for call in self.runner.planning_calls))

    async def test_custom_answer_escape_and_reload_preserve_draft_without_calls(self):
        app = self.make_app([question_response()])
        draft = "Сверять два CSV\nи отдельно комиссии\nБез API ключа"
        async with app.run_test(size=(80, 24)) as pilot:
            await self.submit_rough_request(pilot, app)
            screen = await self.wait_screen(pilot, app, QuestionsScreen)
            await pilot.press("down", "down", "enter")
            screen.query_one("#question-custom", PromptEditor).post_message(events.Paste(draft))
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(app.screen, app._view)
            self.assertEqual(self.intake.state["draft_answers"], {"outcome": draft})
            self.assertEqual(self.runner.execution_calls, [])
            self.assertEqual(len(self.runner.planning_calls), 1)
        resumed = Session.load(self.session.directory)
        resumed.runner = GuidedFixtureRunner([])
        restored = IntakeController(resumed)
        second_app = JevApp(resumed, guided=True, intake=restored)
        async with second_app.run_test(size=(80, 24)) as pilot:
            screen = await self.wait_screen(pilot, second_app, QuestionsScreen)
            self.assertEqual(restored.state["draft_answers"], {"outcome": draft})
            await pilot.click("#question-back")
            screen.query_one(OptionList).focus()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(screen.query_one("#question-custom", PromptEditor).text, draft)
            self.assertEqual(resumed.runner.planning_calls, [])
            self.assertEqual(resumed.runner.execution_calls, [])

    async def test_plan_escape_and_modal_shortcuts_never_execute_background_prompt(self):
        app = self.make_app([plan_response()])
        async with app.run_test(size=(80, 24)) as pilot:
            await self.submit_rough_request(pilot, app)
            await self.wait_screen(pilot, app, PlanScreen)
            app._view.query_one("#prompt", PromptEditor).load_text("Не отправлять из-под модального окна")
            await pilot.press("ctrl+d", "enter")
            self.assertEqual(len(self.runner.planning_calls), 1)
            self.assertEqual(self.runner.execution_calls, [])
            await pilot.press("escape")
            await pilot.pause()
            self.assertIs(app.screen, app._view)
            self.assertEqual(self.intake.state["status"], "plan")
            self.assertTrue(app.query_one("#brief-open", Button).display)
            self.assertEqual(app.query_one("#prompt", PromptEditor).text,
                             "Не отправлять из-под модального окна")
            self.assertEqual(self.runner.execution_calls, [])

    async def test_revise_plan_disables_old_execution_and_preserves_user_feedback(self):
        app = self.make_app([plan_response(), plan_response("Сверка двух CSV")])
        feedback = "Добавь второй CSV\nи покажи расхождения по tx_hash"
        async with app.run_test(size=(80, 24)) as pilot:
            await self.submit_rough_request(pilot, app)
            screen = await self.wait_screen(pilot, app, PlanScreen)
            prior_revision = self.intake.state["revision"]
            await pilot.click("#plan-revise")
            self.assertTrue(screen.query_one("#plan-execute", Button).disabled)
            screen.query_one("#plan-feedback", PromptEditor).post_message(events.Paste(feedback))
            await pilot.pause()
            await pilot.press("enter")
            await self.wait_screen(pilot, app, PlanScreen)
            self.assertGreater(self.intake.state["revision"], prior_revision)
            self.assertIn(feedback, self.intake.state["refined_prompt"])
            self.assertEqual(self.runner.execution_calls, [])
            # A callback held by an old modal cannot accept the replacement plan.
            await pilot.press("escape")
            app._plan_selected({"action": "execute"}, prior_revision)
            await self.wait_idle(pilot, app)
            self.assertEqual(self.runner.execution_calls, [])
            await pilot.click("#brief-open")
            await self.wait_screen(pilot, app, PlanScreen)
            await pilot.click("#plan-execute")
            await self.wait_idle(pilot, app)
            self.assertEqual(len(self.runner.execution_calls), 1)
            self.assertIn(feedback, self.session.history[0]["text"])

    async def test_resume_pending_plan_only_opens_review_and_never_calls_model(self):
        app = self.make_app([plan_response()])
        await self.intake.prepare(ROUGH_REQUEST)
        resumed = Session.load(self.session.directory)
        resumed.runner = GuidedFixtureRunner([])
        restored = IntakeController(resumed)
        app = JevApp(resumed, guided=True, intake=restored)
        async with app.run_test(size=(80, 24)) as pilot:
            await self.wait_screen(pilot, app, PlanScreen)
            self.assertEqual(resumed.runner.planning_calls, [])
            self.assertEqual(resumed.runner.execution_calls, [])
            await pilot.press("escape")
            self.assertEqual(restored.state["status"], "plan")
            self.assertEqual(resumed.history, [])

    async def test_replay_of_plan_and_completed_session_cannot_relaunch(self):
        self.make_app([plan_response()])
        await self.intake.prepare(ROUGH_REQUEST)
        await self.intake.execute(self.intake.state["revision"])
        saved = self.session.events()
        resumed = Session.load(self.session.directory)
        resumed.runner = GuidedFixtureRunner([])
        restored = IntakeController(resumed)
        app = JevApp(resumed, guided=True, intake=restored)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertIs(app.screen, app._view)
            self.assertEqual(restored.state["status"], "completed")
            self.assertFalse(app.query_one("#brief-open").parent.display)
            self.assertEqual(resumed.runner.execution_calls, [])
        replay = JevApp(resumed, replay_events=saved, guided=True, intake=restored)
        async with replay.run_test(size=(80, 24)) as pilot:
            await pilot.press("f5", "ctrl+d")
            await pilot.pause()
            self.assertIs(replay.screen, replay._view)
            self.assertEqual(resumed.runner.planning_calls, [])
            self.assertEqual(resumed.runner.execution_calls, [])

    async def test_narrow_idle_chat_and_question_and_plan_actions_fit(self):
        app = self.make_app([question_response(), plan_response()])
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertGreaterEqual(app.query_one("#chat", VerticalScroll).region.height, 12)
            for selector in ("#nav-new", "#nav-brief", "#nav-menu", "#prompt", "#send-prompt"):
                self.assert_visible(app, selector)
            await self.submit_rough_request(pilot, app)
            screen = await self.wait_screen(pilot, app, QuestionsScreen)
            for selector in ("#question-back", "#question-next", "#question-cancel"):
                self.assert_visible(screen, selector)
            screen = await self.accept_question_defaults(pilot, app)
            for selector in ("#plan-execute", "#plan-revise", "#plan-cancel"):
                self.assert_visible(screen, selector)
            self.assertEqual(self.runner.execution_calls, [])

    async def test_stop_during_planning_returns_to_chat_without_worker(self):
        app = self.make_app([])
        self.runner.pause_planning = True
        async with app.run_test(size=(80, 24)) as pilot:
            await self.submit_rough_request(pilot, app)
            await asyncio.wait_for(self.runner.started.wait(), 2)
            await pilot.pause()
            self.assertTrue(app.query_one("#stop-run", Button).display)
            await pilot.click("#stop-run")
            await self.wait_idle(pilot, app)
            self.assertIs(app.screen, app._view)
            self.assertTrue(self.intake.state["last_error"])
            self.assertFalse(self.session.busy)
            self.assertEqual(self.runner.execution_calls, [])
            self.assertTrue(app.is_running)

    async def test_simple_explanation_answers_without_questionnaire_or_worker(self):
        response = {"kind": "answer", "message": "Объясняю принцип.", "questions": [],
                    "plan": None, "answer": "Jev выбирает типизированные действия; модель пишет ответ."}
        app = self.make_app([response])
        async with app.run_test(size=(80, 24)) as pilot:
            app.query_one("#prompt", PromptEditor).load_text("Как работает Jev?")
            await pilot.press("enter")
            await self.wait_idle(pilot, app)
            self.assertIs(app.screen, app._view)
            self.assertEqual(app._last_answer, response["answer"])
            self.assertEqual(self.runner.execution_calls, [])
            self.assertEqual(self.session.judge.calls, [])
            self.assertEqual(self.session.history, [])


if __name__ == "__main__":
    unittest.main()
