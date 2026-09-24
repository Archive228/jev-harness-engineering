"""Question transitions and actual terminal input; no model calls or writes."""
import unittest

from textual import events
from textual.app import App, ComposeResult
from textual.widgets import Button, OptionList, Static, TabbedContent

from jev_agent.intake_widgets import PlanScreen, QuestionsScreen
from jev_agent.question_state import (create_question_state, question_answers, question_confirm,
                                      question_move, question_save, question_select,
                                      question_set_selected, question_set_tab, question_store_custom,
                                      question_submit, question_sync)
from jev_agent.ui_widgets import PromptEditor


QUESTIONS = [
    {"id": "result", "header": "Outcome", "question": "Что хотите получить для работы с криптой?",
     "options": [{"label": "Локальный отчёт", "description": "Файл с балансом и комиссиями по вашим сделкам."},
                 {"label": "Explanation", "description": "Разобраться в данных без создания программы."}]},
    {"id": "input", "header": "Данные", "question": "Откуда возьмём сделки?",
     "options": [{"label": "Пример CSV", "description": "Создадим понятный пример для первого запуска."},
                 {"label": "Мой файл", "description": "Используем уже подготовленные сделки."}]},
]
PLAN = {"title": "Отчёт по сделкам", "goal": "Запускаемый локальный анализатор CSV.",
        "deliverables": ["CLI", "Markdown-отчёт"],
        "steps": ["Изучить пример данных", "Посчитать суммы", "Проверить отчёт"],
        "acceptance": ["Тесты проверяют комиссии и неверные строки"],
        "constraints": ["Без сети"], "assumptions": ["Входные данные — CSV"],
        "out_of_scope": ["Биржевые сделки"]}


class ModalApp(App):
    def __init__(self, screen):
        super().__init__()
        self.modal = screen
        self.results = []
        self.leaked_submissions = []

    def compose(self) -> ComposeResult:
        yield Static("Existing conversation")

    def on_mount(self):
        self.push_screen(self.modal, self.results.append)

    def on_prompt_editor_submitted(self, event):
        self.leaked_submissions.append(event.text)


class QuestionStateTests(unittest.TestCase):
    def setUp(self):
        self.request = {"id": "q1", "questions": QUESTIONS}

    def test_upstream_equivalent_selection_advances_and_reviews(self):
        state = create_question_state("q1")
        first = question_select(state, self.request)
        self.assertEqual(first.tab, 1)
        self.assertEqual(state.answers, [])
        second = question_select(question_set_selected(first, 1), self.request)
        self.assertTrue(question_confirm(self.request, second))
        self.assertEqual(question_submit(self.request, second),
                         {"requestID": "q1", "answers": [["Локальный отчёт"], ["Мой файл"]]})

    def test_single_question_also_requires_review(self):
        request = {"id": "q1", "questions": QUESTIONS[:1]}
        state = question_select(create_question_state("q1"), request)
        self.assertTrue(question_confirm(request, state))
        self.assertFalse(state.submitting)
        self.assertEqual(question_submit(request, state)["answers"], [["Локальный отчёт"]])

    def test_custom_answer_and_back_edit_do_not_retain_old_value(self):
        state = question_select(question_set_selected(create_question_state("q1"), 2), self.request)
        self.assertTrue(state.editing)
        state = question_store_custom(state, 0, "  Мой вариант\nс деталями  ")
        state = question_save(state, self.request)
        self.assertEqual(state.answers[0], ["Мой вариант\nс деталями"])
        state = question_set_tab(state, 0)
        state = question_store_custom(state, 0, "Новый вариант")
        state = question_save(state, self.request)
        self.assertEqual(state.answers[0], ["Новый вариант"])

    def test_empty_custom_cannot_advance_or_supply_consent(self):
        state = question_store_custom(create_question_state("q1"), 0, " \n ")
        self.assertEqual(question_save(state, self.request).tab, 0)
        with self.assertRaises(ValueError):
            question_submit(self.request, question_set_tab(state, 2))

    def test_request_reset_and_navigation_wrap(self):
        state = question_set_selected(create_question_state("q1"), 2)
        self.assertIs(question_sync(state, "q1"), state)
        self.assertEqual(question_sync(state, "q2"), create_question_state("q2"))
        self.assertEqual(question_move(state, self.request, 1).selected, 0)
        self.assertEqual(question_move(create_question_state("q1"), self.request, -1).selected, 2)

    def test_returned_answer_lists_do_not_alias_saved_state(self):
        state = question_select(create_question_state("q1"), self.request)
        values = question_answers(state, 2)
        values[0].append("unwanted edit")
        self.assertEqual(state.answers, [["Локальный отчёт"]])


class QuestionScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_choices_review_then_return_bare_labels_only(self):
        drafts = []
        screen = QuestionsScreen(QUESTIONS, on_draft=drafts.append)
        app = ModalApp(screen)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            # A highlighted recommendation is not yet an answer.
            await pilot.click("#question-next")
            self.assertEqual(screen.state.tab, 0)
            self.assertEqual(drafts, [])
            screen.query_one(OptionList).focus()
            await pilot.press("enter", "down", "enter")
            await pilot.pause()
            self.assertEqual(app.results, [])
            self.assertTrue(question_confirm(screen.request, screen.state))
            self.assertEqual(drafts[-1], {"result": "Локальный отчёт", "input": "Мой файл"})
            await pilot.click("#question-next")
            self.assertEqual(app.results, [{"result": "Локальный отчёт", "input": "Мой файл"}])

    async def test_custom_multiline_paste_persists_and_enter_stays_in_modal(self):
        drafts = []
        screen = QuestionsScreen(QUESTIONS[:1], on_draft=drafts.append)
        app = ModalApp(screen)
        text = "Хочу сверять мои сделки\nс двумя CSV\nи отдельно комиссии"
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("down", "down", "enter")
            await pilot.pause()
            editor = screen.query_one("#question-custom", PromptEditor)
            self.assertTrue(editor.has_focus)
            editor.post_message(events.Paste(text))
            await pilot.pause()
            self.assertEqual(editor.text, text)
            self.assertEqual(drafts[-1], {"result": text})
            self.assertEqual(app.results, [])
            await pilot.press("enter")
            await pilot.pause()
            self.assertTrue(question_confirm(screen.request, screen.state))
            self.assertEqual(app.leaked_submissions, [])
            await pilot.click("#question-next")
            self.assertEqual(app.results, [{"result": text}])

    async def test_escape_keeps_custom_draft_without_reply(self):
        drafts = []
        app = ModalApp(QuestionsScreen(QUESTIONS, on_draft=drafts.append))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("down", "down", "enter")
            editor = app.screen.query_one("#question-custom", PromptEditor)
            editor.post_message(events.Paste("Мой незаконченный ответ"))
            await pilot.pause()
            await pilot.press("escape")
            self.assertEqual(app.results, [None])
            self.assertEqual(drafts[-1], {"result": "Мой незаконченный ответ"})

    async def test_restore_answers_then_back_and_change(self):
        screen = QuestionsScreen(QUESTIONS, {"result": "Локальный отчёт", "input": "Мой файл"})
        app = ModalApp(screen)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertTrue(question_confirm(screen.request, screen.state))
            await pilot.click("#question-back")
            self.assertEqual(screen.state.tab, 1)
            await pilot.press("up", "enter")
            await pilot.click("#question-next")
            self.assertEqual(app.results, [{"result": "Локальный отчёт", "input": "Пример CSV"}])

    async def test_compact_layout_question_and_actions_are_reachable(self):
        screen = QuestionsScreen(QUESTIONS)
        async with ModalApp(screen).run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            for selector in ("#questions-heading", "#question-text", "#question-next", "#question-cancel"):
                region = screen.query_one(selector).region
                self.assertGreater(region.width, 0)
                self.assertGreaterEqual(region.y, 0)
                self.assertLessEqual(region.bottom, 24)
                self.assertLessEqual(region.right, 80)
            await pilot.resize_terminal(110, 38)
            await pilot.resize_terminal(80, 24)
            self.assertEqual(screen.state.answers, [[], []])

    async def test_oversized_paste_stays_editable_and_cannot_submit(self):
        drafts = []
        screen = QuestionsScreen(QUESTIONS[:1], on_draft=drafts.append)
        app = ModalApp(screen)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("down", "down", "enter")
            editor = screen.query_one("#question-custom", PromptEditor)
            editor.post_message(events.Paste("x" * 5000))
            await pilot.pause()
            self.assertEqual(editor.text, "x" * 5000)
            self.assertIn("4000", str(screen.query_one("#questions-notice", Static).renderable))
            await pilot.press("enter")
            self.assertEqual(screen.state.tab, 0)
            self.assertEqual(app.results, [])
            editor.load_text("Короткий ответ")
            await pilot.pause()
            self.assertNotIn("4000", str(screen.query_one("#questions-notice", Static).renderable))
            await pilot.press("enter")
            await pilot.click("#question-next")
            self.assertEqual(app.results, [{"result": "Короткий ответ"}])

    async def test_draft_save_error_is_visible_without_crashing_or_submitting(self):
        def fail_save(_):
            raise OSError("Диск недоступен")
        screen = QuestionsScreen(QUESTIONS[:1], on_draft=fail_save)
        app = ModalApp(screen)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("down", "down", "enter")
            editor = screen.query_one("#question-custom", PromptEditor)
            editor.post_message(events.Paste("Мой ответ"))
            await pilot.pause()
            self.assertEqual(editor.text, "Мой ответ")
            self.assertIn("Диск недоступен", str(screen.query_one("#questions-notice", Static).renderable))
            await pilot.press("enter")
            self.assertEqual(screen.state.tab, 0)
            self.assertEqual(app.results, [])

    async def test_wide_question_card_does_not_fill_blank_screen(self):
        screen = QuestionsScreen(QUESTIONS)
        async with ModalApp(screen).run_test(size=(116, 42)) as pilot:
            await pilot.pause()
            self.assertLessEqual(screen.query_one("#questions-box").region.height, 24)


class PlanScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_plan_disables_button_and_guards_forged_event(self):
        screen = PlanScreen(PLAN, can_execute=False, notice="Только план: включите /mode auto.")
        app = ModalApp(screen)
        async with app.run_test(size=(80, 24)) as pilot:
            button = screen.query_one("#plan-execute", Button)
            self.assertTrue(button.disabled)
            self.assertIn("/mode auto", str(screen.query_one("#plan-notice", Static).renderable))
            screen.on_button_pressed(Button.Pressed(button))
            await pilot.pause()
            self.assertEqual(app.results, [])
            self.assertLessEqual(screen.query_one("#plan-revise").region.bottom, 24)

    async def test_plan_opens_without_execution_and_exact_prompt_is_visible(self):
        prompt = "Исходный запрос\nПодтверждённый результат\n[not markup]"
        screen = PlanScreen(PLAN, "хочу крипту", prompt)
        app = ModalApp(screen)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertEqual(app.results, [])
            self.assertEqual(screen.query_one("#plan-exact-prompt", Static).renderable.plain, prompt)
            self.assertIn("How we check", screen.query_one("#plan-summary", Static).renderable.plain)
            region = screen.query_one("#plan-execute").region
            self.assertLessEqual(region.bottom, 24)
            self.assertLessEqual(region.right, 80)
            await pilot.click("#plan-execute")
            self.assertEqual(app.results, [{"action": "execute"}])

    async def test_revision_preserves_multiline_and_cannot_execute(self):
        screen = PlanScreen(PLAN)
        app = ModalApp(screen)
        feedback = "Без API\nи нужен HTML вместо Markdown"
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#plan-revise")
            self.assertTrue(screen.query_one("#plan-execute", Button).disabled)
            editor = screen.query_one("#plan-feedback", PromptEditor)
            editor.post_message(events.Paste(feedback))
            await pilot.pause()
            self.assertEqual(app.results, [])
            await pilot.press("enter")
            self.assertEqual(app.results, [{"action": "revise", "feedback": feedback}])
            self.assertEqual(app.leaked_submissions, [])

    async def test_plan_cancel_never_executes(self):
        app = ModalApp(PlanScreen(PLAN))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("escape")
            self.assertEqual(app.results, [None])

    async def test_long_plan_scrolls_with_actions_fixed(self):
        plan = dict(PLAN, steps=["Проверить данные и сформировать подробный отчёт " * 5 for _ in range(10)])
        screen = PlanScreen(plan)
        async with ModalApp(screen).run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            scroll = screen.query_one("#plan-summary-tab .plan-scroll")
            self.assertGreater(scroll.virtual_size.height, scroll.size.height)
            self.assertLessEqual(screen.query_one("#plan-execute").region.bottom, 24)
            await pilot.press("pagedown")
            await pilot.pause(.2)
            self.assertGreater(scroll.scroll_y, 0)


if __name__ == "__main__":
    unittest.main()
