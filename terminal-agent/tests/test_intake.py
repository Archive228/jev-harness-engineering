"""The intent conversation cannot execute work without a current accepted plan."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from jev_agent.core import Session, snapshot, write_json
from jev_agent.intake import IntakeController, INTAKE_SCHEMA, compile_brief, validate_response
from test_engine import FixtureJudge


def question_response():
    return {"kind": "questions", "message": "Выберем результат.", "questions": [{
        "id": "outcome", "header": "Результат", "question": "Что хотим получить?",
        "options": [{"label": "Анализ CSV", "description": "Локальный отчёт по сделкам."},
                    {"label": "Трекер", "description": "Список позиций."}]}],
        "plan": None, "answer": ""}


def plan_response():
    return {"kind": "plan", "message": "Сделаем локальный отчёт.", "questions": [], "plan": {
        "title": "Анализ сделок из CSV", "goal": "Пользователь получает проверенный отчёт.",
        "deliverables": ["report.py и пример trades.csv"],
        "steps": ["Проверить формат входных данных.", "Реализовать расчёт.", "Проверить известный пример."],
        "acceptance": ["На покупке 1 BTC за 10 и продаже за 12 результат равен 2 до комиссии."],
        "constraints": ["Без сети."], "assumptions": ["Одна валюта расчёта."],
        "out_of_scope": ["Отправка торговых ордеров."]}, "answer": ""}


def answer_response():
    return {"kind": "answer", "message": "Краткий ответ.", "questions": [], "plan": None,
            "answer": "Jev возвращает типизированные решения, а код пишет worker."}


class IntakeRunner:
    def __init__(self, responses, action=None):
        self.responses = list(responses)
        self.action = action
        self.calls = []

    async def run(self, prompt, workspace, directory, emit, cancel_event, readonly=False, schema=None):
        self.calls.append({"prompt": prompt, "readonly": readonly, "schema": schema, "directory": directory})
        if self.action:
            self.action(workspace)
        response = self.responses.pop(0) if schema is not None else "Готово; фикстура не вызывает API."
        if isinstance(response, Exception):
            raise response
        text = json.dumps(response, ensure_ascii=False) if isinstance(response, dict) else response
        emit("message", role="assistant", text=text)
        return {"text": text, "completed": True, "usage": {"input_tokens": 10, "output_tokens": 3}}


class BlockingIntakeRunner(IntakeRunner):
    def __init__(self):
        super().__init__([])
        self.started = asyncio.Event()

    async def run(self, prompt, workspace, directory, emit, cancel_event, readonly=False, schema=None):
        self.started.set()
        await cancel_event.wait()
        raise asyncio.CancelledError()


class IntakeValidationTests(unittest.TestCase):
    def test_provider_schema_requires_all_fields_and_no_extra_fields(self):
        self.assertEqual(set(INTAKE_SCHEMA["required"]), set(INTAKE_SCHEMA["properties"]))
        self.assertFalse(INTAKE_SCHEMA["additionalProperties"])
        self.assertEqual(INTAKE_SCHEMA["properties"]["questions"]["maxItems"], 3)

    def test_duplicate_ids_are_rejected(self):
        response = question_response()
        response["questions"].append(copy.deepcopy(response["questions"][0]))
        with self.assertRaises(ValueError):
            validate_response(response)

    def test_missing_fields_and_invalid_branch_mix_are_rejected(self):
        cases = [question_response(), plan_response(), answer_response()]
        cases[0].pop("answer")
        cases[1]["questions"] = question_response()["questions"]
        cases[2]["plan"] = plan_response()["plan"]
        for response in cases:
            with self.subTest(response=response), self.assertRaises(ValueError):
                validate_response(response)

    def test_recommendation_is_presentation_and_duplicate_bare_options_fail(self):
        response = question_response()
        response["questions"][0]["options"][0]["label"] += " (Recommended)"
        self.assertEqual(validate_response(response)["questions"][0]["options"][0]["label"], "Анализ CSV")
        response["questions"][0]["options"][1]["label"] = "Анализ CSV"
        with self.assertRaises(ValueError):
            validate_response(response)

    def test_blank_provider_summary_gets_safe_branch_specific_fallback(self):
        for kind, expected in (("questions", "Уточним несколько деталей"),
                               ("plan", "План готов"),
                               ("answer", "Ответ готов")):
            response = question_response() if kind == "questions" else plan_response() if kind == "plan" else answer_response()
            response["kind"] = kind
            response["message"] = " \n "
            if kind == "questions":
                response["plan"] = None
            elif kind == "plan":
                response["questions"] = []
            else:
                response["questions"] = []
                response["plan"] = None
            self.assertIn(expected, validate_response(response)["message"])


class IntakeFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Session.create(Path(self.temp.name) / "sessions")
        self.session.judge = FixtureJudge()

    def controller(self, responses, action=None):
        self.session.runner = IntakeRunner(responses, action)
        return IntakeController(self.session)

    async def test_vague_request_questions_answers_plan_then_explicit_execution(self):
        controller = self.controller([question_response(), plan_response()])
        events = []
        questions = await controller.prepare("Сделай что-то про крипту", events.append)
        self.assertEqual(questions["status"], "questions")
        self.assertFalse(self.session.busy)
        self.assertEqual(self.session.metadata["title"], "Сделай что-то про крипту")
        self.assertEqual(snapshot(self.session.workspace)["files"], {})
        self.assertTrue(self.session.runner.calls[0]["readonly"])
        self.assertIs(self.session.runner.calls[0]["schema"], INTAKE_SCHEMA)
        self.assertFalse(any(event["type"] in {"message", "end", "jev"} for event in events))
        self.assertEqual(questions["planner_meters"]["planner_tokens"], 13)
        controller.save_draft_answers({"outcome": "Анализ CSV"})
        planned = await controller.prepare("", events.append, answers={"outcome": "Анализ CSV"})
        self.assertEqual(planned["status"], "plan")
        self.assertIn("Что хотим получить?\nОтвет: Анализ CSV", planned["refined_prompt"])
        self.assertIn("Предположения, а не факты", planned["refined_prompt"])
        self.assertEqual(len(self.session.judge.calls), 0)
        self.assertEqual(self.session.runner.calls[1]["readonly"], True)
        self.assertEqual(len(list(self.session.directory.glob("turn-*"))), 0)
        result = await controller.execute(planned["revision"], events.append)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(controller.state["status"], "completed")
        self.assertGreater(len(self.session.judge.calls), 0)
        self.assertFalse(self.session.runner.calls[-1]["readonly"])
        self.assertIn("План принят:", [event["data"]["text"] for event in events if event["type"] == "user"][-1])
        request_path = next(self.session.directory.glob("turn-*/request.json"))
        self.assertEqual(json.loads(request_path.read_text())["text"], planned["refined_prompt"])

    async def test_missing_or_unknown_answers_do_not_start_planner(self):
        controller = self.controller([question_response()])
        await controller.prepare("Хочу проект")
        for answers in ({}, {"obsolete": "1"}, {"outcome": ""}, {"outcome": "(Recommended)"}):
            with self.subTest(answers=answers), self.assertRaises(ValueError):
                await controller.prepare("", answers=answers)
        self.assertEqual(len(self.session.runner.calls), 1)

    async def test_draft_survives_restart_but_does_not_become_locked_answer(self):
        controller = self.controller([question_response()])
        await controller.prepare("Хочу проект")
        controller.save_draft_answers({"outcome": "Мой формат\nс двумя строками"})
        restored = IntakeController(self.session)
        self.assertEqual(restored.state["draft_answers"]["outcome"], "Мой формат\nс двумя строками")
        self.assertEqual(restored.state["answers"], [])
        self.assertEqual(len(self.session.runner.calls), 1)

    async def test_malformed_json_preserves_question_and_entered_answers(self):
        controller = self.controller([question_response(), "not JSON"])
        await controller.prepare("Крипта")
        failed = await controller.prepare("", answers={"outcome": "CSV"})
        self.assertEqual(failed["status"], "questions")
        self.assertTrue(failed["last_error"])
        self.assertEqual(failed["draft_answers"], {"outcome": "CSV"})
        self.assertEqual(failed["answers"][-1]["answer"], "CSV")
        self.assertFalse(self.session.busy)

    async def test_failed_plan_revision_is_recoverable_after_restart(self):
        controller = self.controller([plan_response(), "not JSON"])
        await controller.prepare("Сделай отчёт CSV")
        await controller.prepare("Добавь комиссии")
        restored = IntakeController(self.session)
        self.assertEqual(restored.state["status"], "plan")
        self.assertEqual(restored.state["revisions"], ["Добавь комиссии"])
        self.assertTrue(restored.state["last_error"])
        with self.assertRaises(ValueError):
            await restored.execute(restored.state["revision"])

    async def test_cancel_retains_request_and_never_executes(self):
        runner = BlockingIntakeRunner()
        self.session.runner = runner
        controller = IntakeController(self.session)
        task = asyncio.create_task(controller.prepare("Сделай отчёт"))
        await runner.started.wait()
        self.assertTrue(self.session.busy)
        self.session.cancel()
        state = await task
        self.assertEqual(state["status"], "idle")
        self.assertIn("остановлена", state["last_error"])
        self.assertFalse(self.session.busy)
        self.assertIsNone(self.session._emit_callback)
        self.assertFalse(list(self.session.directory.glob("turn-*")))

    async def test_no_execution_before_plan_or_with_stale_revision(self):
        controller = self.controller([question_response(), plan_response(), plan_response()])
        await controller.prepare("Крипта")
        with self.assertRaises(ValueError):
            await controller.execute(controller.state["revision"])
        plan = await controller.prepare("", answers={"outcome": "CSV"})
        await controller.prepare("Учти комиссию")
        for revision in (plan["revision"], True, "3"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                await controller.execute(revision)
        self.assertEqual(len(self.session.judge.calls), 0)

    async def test_changed_workspace_invalidates_plan(self):
        controller = self.controller([plan_response()])
        state = await controller.prepare("Сделай отчёт")
        (self.session.workspace / "user-change.txt").write_text("concurrent edit")
        with self.assertRaisesRegex(ValueError, "проект изменился"):
            await controller.execute(state["revision"])
        self.assertEqual(controller.state["status"], "plan")
        self.assertTrue(controller.state["last_error"])
        self.assertEqual(len(self.session.runner.calls), 1)

    async def test_changed_workspace_during_readonly_planning_is_rejected(self):
        controller = self.controller([plan_response()], action=lambda root: (root / "unexpected.txt").write_text("write"))
        state = await controller.prepare("Сделай отчёт")
        self.assertEqual(state["status"], "idle")
        self.assertIn("изменились файлы", state["last_error"])
        self.assertFalse(self.session.busy)
        self.assertTrue((self.session.workspace / "unexpected.txt").is_file())
        self.assertTrue((self.session.directory / "intake/round-001/snapshot-after.json").is_file())

    async def test_plan_mode_cannot_approve_execution(self):
        controller = self.controller([plan_response()])
        state = await controller.prepare("Сделай отчёт")
        self.session.configure(execution_mode="plan")
        with self.assertRaisesRegex(ValueError, "Только план"):
            await controller.execute(state["revision"])
        self.assertEqual(len(self.session.runner.calls), 1)

    async def test_duplicate_execute_is_blocked_before_first_await_finishes(self):
        controller = self.controller([plan_response()])
        state = await controller.prepare("Сделай отчёт")
        first = asyncio.create_task(controller.execute(state["revision"]))
        await asyncio.sleep(0)
        with self.assertRaises(ValueError):
            await controller.execute(state["revision"])
        await first
        self.assertEqual(len([call for call in self.session.runner.calls if not call["readonly"]]), 1)

    async def test_stop_during_approval_snapshot_prevents_execution(self):
        controller = self.controller([plan_response()])
        state = await controller.prepare("Сделай отчёт")
        entered, released = threading.Event(), threading.Event()

        def slow_snapshot(workspace):
            entered.set()
            if not released.wait(5):
                raise AssertionError("Test did not release snapshot")
            return snapshot(workspace)

        with patch("jev_agent.intake.snapshot", slow_snapshot):
            execution = asyncio.create_task(controller.execute(state["revision"]))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                self.assertTrue(self.session.busy)
                with self.assertRaises(ValueError):
                    self.session.configure(execution_mode="plan")
                self.session.cancel()
            finally:
                released.set()
            with self.assertRaisesRegex(RuntimeError, "Запуск остановлен"):
                await execution
        self.assertFalse(self.session.busy)
        self.assertEqual(controller.state["status"], "plan")
        self.assertIn("Выполнение не начиналось", controller.state["last_error"])
        self.assertEqual(self.session.judge.calls, [])
        self.assertFalse(list(self.session.directory.glob("turn-*")))
        self.assertEqual(len(self.session.runner.calls), 1)

    async def test_load_interrupted_state_never_runs_and_requires_refresh(self):
        controller = self.controller([plan_response()])
        state = await controller.prepare("Сделай отчёт")
        state["status"] = "executing"
        write_json(controller.path, state)
        restored = IntakeController(self.session)
        self.assertEqual(restored.state["status"], "plan")
        self.assertTrue(restored.state["interrupted"])
        with self.assertRaises(ValueError):
            await restored.execute(restored.state["revision"])
        self.assertEqual(len(self.session.runner.calls), 1)

    async def test_corrupt_or_oversized_state_does_not_raise_on_startup(self):
        controller = self.controller([])
        for content in ("{bad", "x" * 1_000_001):
            controller.path.write_text(content)
            restored = IntakeController(self.session)
            self.assertEqual(restored.state["status"], "idle")
            self.assertTrue(restored.state["last_error"])
        self.assertEqual(self.session.runner.calls, [])

    async def test_answer_bypasses_form_and_next_request_starts_fresh(self):
        controller = self.controller([answer_response(), question_response()])
        answered = await controller.prepare("Что такое Jev?")
        self.assertEqual(answered["status"], "answer")
        self.assertFalse(list(self.session.directory.glob("turn-*")))
        next_state = await controller.prepare("Сделай что-нибудь про крипту")
        self.assertEqual(next_state["original"], "Сделай что-нибудь про крипту")
        self.assertEqual(next_state["revisions"], [])
        self.assertEqual(next_state["status"], "questions")

    async def test_compiled_request_limit_is_checked_without_execution(self):
        controller = self.controller([plan_response()])
        state = await controller.prepare("Описание " + "а" * 19600)
        self.assertTrue(state["last_error"])
        self.assertIn("20000", state["last_error"])
        self.assertTrue((self.session.directory / "intake/round-001/response.json").is_file())
        self.assertEqual(len(self.session.judge.calls), 0)

    async def test_compiled_request_limit_preserves_answers_for_recovery(self):
        controller = self.controller([question_response(), plan_response()])
        await controller.prepare("Описание " + "а" * 19000)
        answer = "Описание формата " + "б" * 2000
        controller.save_draft_answers({"outcome": answer})
        state = await controller.prepare("", answers={"outcome": answer})
        self.assertIn("20000", state["last_error"])
        self.assertEqual(state["status"], "questions")
        self.assertEqual(state["draft_answers"], {"outcome": answer})
        restored = IntakeController(self.session)
        self.assertEqual(restored.state["draft_answers"], {"outcome": answer})
        self.assertEqual(self.session.judge.calls, [])

    async def test_bound_workspace_context_is_supplied_with_real_checks(self):
        (self.session.workspace / "README.md").write_text("CSV parser handles trades")
        (self.session.workspace / ".env").write_text("PRIVATE=unused")
        controller = self.controller([plan_response()])
        await controller.prepare("Сделай отчёт CSV")
        prompt = self.session.runner.calls[0]["prompt"]
        self.assertIn("README.md", prompt)
        self.assertIn("CSV parser handles trades", prompt)
        self.assertNotIn("PRIVATE=unused", prompt)
        self.assertIn('"registered_checks": []', prompt)

    async def test_failed_persistence_does_not_leave_busy_lock(self):
        controller = self.controller([plan_response()])
        with patch.object(controller, "_save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await controller.prepare("Сделай отчёт")
        self.assertFalse(self.session.busy)
        self.assertEqual(controller.state["status"], "idle")


if __name__ == "__main__":
    unittest.main()
