"""The turn policy: thresholds as data, one pure verdict, and replay from the journal."""
import io
import json
from pathlib import Path
import contextlib
import sys
import tempfile
import unittest

from jev_agent.cli import main
from jev_agent.core import Session
from jev_agent.decision import (POLICY_VERSION, THRESHOLDS, decide_turn, report_summary,
                                requirement_gaps, requirement_key, review_summary,
                                route_uncertain, thresholds, triage_applies)
from jev_agent.replay import read_decisions, replay_session
from jev_agent.runtime import RuntimeFailure


PASSING = {"passed": 1, "total": 1, "fresh": True, "registered": True}
FAILING = {"passed": 0, "total": 1, "fresh": True, "registered": True}
UNREGISTERED = {"passed": 1, "total": 1, "fresh": True, "registered": False}


def review(action="finish", confidence=1.0, addresses=1.0):
    return {"action": action, "confidence": confidence, "addresses_request": addresses}


def decide(**overrides):
    call = {"attempt": 1, "readonly": False, "changed": 1, "report": None,
            "review": review(), "judge_state": "applied"}
    call.update(overrides)
    return decide_turn(**call)


class ThresholdTests(unittest.TestCase):
    def test_every_bar_the_executor_uses_lives_in_one_place(self):
        self.assertEqual(set(THRESHOLDS), {
            "max_attempts", "route_min_confidence", "triage_min_confidence",
            "triage_min_probability", "improve_min_confidence", "addresses_request_min_noul",
            "requirement_closed_min_noul"})
        self.assertIsNot(thresholds(), THRESHOLDS)  # A caller cannot mutate the policy.

    def test_unknown_or_malformed_overrides_are_rejected_not_ignored(self):
        for override in ({"nonexistent": 0.5}, {"improve_min_confidence": "0.6"},
                         {"improve_min_confidence": True}, {"improve_min_confidence": 1.5},
                         {"improve_min_confidence": -0.1}, {"max_attempts": 0},
                         {"max_attempts": 2.5}):
            with self.assertRaises(ValueError):
                thresholds(override)

    def test_accepted_overrides_are_normalised(self):
        policy = thresholds({"max_attempts": 2, "improve_min_confidence": 0})
        self.assertEqual(policy["max_attempts"], 2)
        self.assertEqual(policy["improve_min_confidence"], 0.0)
        self.assertEqual(policy["route_min_confidence"], THRESHOLDS["route_min_confidence"])

    def test_route_and_triage_bars_are_read_from_the_policy(self):
        self.assertTrue(route_uncertain(0.24))
        self.assertFalse(route_uncertain(0.25))
        self.assertFalse(route_uncertain(0.1, thresholds({"route_min_confidence": 0.05})))
        confident = {"choice": "code", "confidence": 0.55, "probabilities": {"code": 0.65, "other": 0.35}}
        self.assertTrue(triage_applies(confident))
        self.assertFalse(triage_applies({**confident, "confidence": 0.54}))
        self.assertFalse(triage_applies({**confident, "probabilities": {"code": 0.64, "other": 0.36}}))


class VerdictTests(unittest.TestCase):
    def test_unavailable_judge_never_yields_acceptance(self):
        # The defect this replaces: a missing review used to count as confidence 1.0,
        # so an outage made automatic acceptance more likely, not less.
        verdict = decide(report=PASSING, review=None, judge_state="unavailable")
        self.assertEqual(verdict["outcome"], "return")
        self.assertEqual((verdict["status"], verdict["reason"]), ("needs_input", "judge_unavailable"))

    def test_judge_not_consulted_leaves_the_decision_to_python_policy(self):
        verdict = decide(report=PASSING, review=None, judge_state="not_consulted")
        self.assertEqual((verdict["status"], verdict["reason"]), ("accepted", "registered_checks_passed"))

    def test_failed_check_outranks_a_confident_finish(self):
        retry = decide(report=FAILING, changed=2)
        self.assertEqual(retry["outcome"], "retry")
        self.assertTrue(retry["checks_blocked"])
        for stop in (decide(report=FAILING, changed=0), decide(report=FAILING, attempt=3)):
            self.assertEqual((stop["status"], stop["reason"]),
                             ("stopped", "checks_failed_or_no_progress"))
            self.assertTrue(stop["checks_blocked"])

    def test_stale_snapshot_blocks_completion_even_when_every_check_passed(self):
        stale = decide(report={**PASSING, "fresh": False}, changed=0)
        self.assertEqual((stale["status"], stale["reason"]), ("stopped", "checks_failed_or_no_progress"))

    def test_confident_improve_retries_until_progress_or_the_attempt_limit(self):
        self.assertEqual(decide(review=review("improve", 0.6))["outcome"], "retry")
        for stop in (decide(review=review("improve", 0.6), changed=0),
                     decide(review=review("improve", 0.6), attempt=3)):
            self.assertEqual((stop["status"], stop["reason"]),
                             ("stopped", "iteration_limit_or_no_progress"))
            self.assertEqual(stop["threshold"], "improve_min_confidence")

    def test_attempt_limit_comes_from_the_policy_not_from_a_literal(self):
        policy = thresholds({"max_attempts": 2})
        self.assertEqual(decide_turn(attempt=2, readonly=False, changed=1, report=None,
                                     review=review("improve", 0.9), judge_state="applied",
                                     policy=policy)["outcome"], "return")
        self.assertEqual(decide_turn(attempt=2, readonly=False, changed=1, report=None,
                                     review=review("improve", 0.9), judge_state="applied")["outcome"], "retry")

    def test_readonly_turn_never_retries_on_improve(self):
        verdict = decide(readonly=True, review=review("improve", 0.9))
        self.assertEqual((verdict["status"], verdict["reason"]),
                         ("answered", "response_prepared_without_independent_acceptance"))

    def test_uncertainty_asks_the_user_and_names_the_bar_that_applied(self):
        asked = decide(review=review("ask_user"))
        self.assertEqual((asked["status"], asked["reason"]), ("needs_input", "review_requests_clarification"))
        unaddressed = decide(review=review(addresses=0.49))
        self.assertEqual(unaddressed["reason"], "uncertain_request_correspondence")
        self.assertEqual(unaddressed["threshold"], "addresses_request_min_noul")

    def test_an_unconfident_improve_does_not_send_the_user_away(self):
        # It means "no opinion", not "something is wrong": the turn ends on its
        # own merits, and correspondence to the request is what can still stop it.
        unsure = decide(review=review("improve", 0.26, addresses=0.75))
        self.assertEqual((unsure["status"], unsure["reason"]),
                         ("ready", "response_prepared_without_independent_acceptance"))
        still_asks = decide(review=review("improve", 0.26, addresses=0.2))
        self.assertEqual(still_asks["reason"], "uncertain_request_correspondence")

    def test_acceptance_requires_a_registered_contract(self):
        self.assertEqual(decide(report=PASSING)["status"], "accepted")
        self.assertEqual(decide(report=UNREGISTERED)["status"], "ready")
        self.assertEqual(decide(report=None)["status"], "ready")

    def test_unknown_judge_state_is_an_error_not_a_default(self):
        with self.assertRaises(ValueError):
            decide(judge_state="maybe")

    def test_summaries_carry_only_the_facts_the_policy_reads(self):
        self.assertIsNone(report_summary(None))
        self.assertIsNone(review_summary(None))
        self.assertEqual(report_summary({"passed": 1, "total": 2, "fresh": True, "registered": 1,
                                         "items": [{"output": "secret"}], "stage": "attempt-01"}),
                         {"passed": 1, "total": 2, "fresh": True, "registered": True})
        self.assertEqual(review_summary({"next_action": {"choice": "finish", "confidence": 0.8,
                                                         "probabilities": {"finish": 0.9}},
                                         "addresses_request": {"noul": 0.7}}),
                         {"action": "finish", "confidence": 0.8, "addresses_request": 0.7})


class RequirementGapTests(unittest.TestCase):
    REQUIREMENTS = ["CLI печатает отчёт", "Тесты проходят", "README обновлён"]

    def _answers(self, *values):
        return {requirement_key(i): {"type": "noul", "noul": v}
                for i, v in enumerate(values) if v is not None}

    def test_only_requirements_judged_below_the_bar_are_reported_open(self):
        gaps = requirement_gaps(self._answers(0.9, 0.2, 0.49), self.REQUIREMENTS)
        self.assertEqual([gap["index"] for gap in gaps], [2, 3])
        self.assertEqual(gaps[0]["requirement"], "Тесты проходят")
        self.assertEqual(gaps[0]["closed_noul"], 0.2)

    def test_a_requirement_without_an_answer_is_not_treated_as_a_finding(self):
        self.assertEqual(requirement_gaps(self._answers(0.9, None, 0.1), self.REQUIREMENTS)[0]["index"], 3)
        self.assertEqual(requirement_gaps({}, self.REQUIREMENTS), [])
        self.assertEqual(requirement_gaps(None, self.REQUIREMENTS), [])

    def test_a_malformed_answer_is_ignored_rather_than_counted(self):
        answers = {requirement_key(0): {"type": "noul", "noul": True},
                   requirement_key(1): {"type": "noul", "noul": "0.1"},
                   requirement_key(2): "not a dict"}
        self.assertEqual(requirement_gaps(answers, self.REQUIREMENTS), [])

    def test_the_bar_comes_from_the_policy(self):
        strict = thresholds({"requirement_closed_min_noul": 0.95})
        self.assertEqual(len(requirement_gaps(self._answers(0.9, 0.2, 0.99), self.REQUIREMENTS, strict)), 2)

    def test_gaps_are_advisory_and_never_reach_the_verdict(self):
        # Acceptance belongs to executed checks; an open requirement must not
        # block a turn whose registered contract passed.
        verdict = decide(report=PASSING, review=review())
        self.assertEqual(verdict["status"], "accepted")


class RoutingJudge:
    """Answers routing and context, then fails exactly like a lost review call."""
    def __init__(self, fail_on="review"):
        self.fail_on = fail_on
        self.purposes = []

    async def ask(self, state, questions, directory, emit, cancel_event):
        purpose = "review" if "next_action" in questions else "route" if "route" in questions else "other"
        self.purposes.append(purpose)
        if purpose == self.fail_on:
            raise RuntimeFailure("Jev API недоступен")
        answers = {}
        for key, question in questions.items():
            if question["type"] == "noul":
                answers[key] = {"type": "noul", "noul": 1.0}
            else:
                choice = "implement" if key == "route" else "finish"
                answers[key] = {"type": "choice", "choice": choice, "confidence": 1.0,
                                "probabilities": {k: float(k == choice) for k in question["criteria"]}}
        return {"model": "fixture-only", "answers": answers,
                "usage": {"input_tokens": 5, "output_tokens": 2}}


class QuietRunner:
    def __init__(self, action=None):
        self.action = action
        self.calls = []

    async def run(self, prompt, workspace, directory, emit, cancel_event, readonly=False, schema=None):
        self.calls.append({"readonly": readonly, "prompt": prompt})
        if self.action:
            self.action(workspace)
        return {"text": "Готово: файл создан.", "usage": {"input_tokens": 9, "output_tokens": 4},
                "completed": True}


class GapJudge:
    """Judges one approved requirement unmet and asks for another attempt."""
    def __init__(self, action="improve"):
        self.action = action
        self.asked = []

    async def ask(self, state, questions, directory, emit, cancel_event):
        self.asked.append(sorted(questions))
        answers = {}
        for key, question in questions.items():
            if question["type"] == "noul":
                answers[key] = {"type": "noul", "noul": 0.1 if key == requirement_key(0) else 0.95}
                continue
            choice = "implement" if key == "route" else "code" if key == "category" else self.action
            others = [name for name in question["criteria"] if name != choice]
            share = round(0.1 / len(others), 4) if others else 0.0
            probabilities = {name: share for name in others}
            probabilities[choice] = round(1.0 - share * len(others), 4)
            answers[key] = {"type": "choice", "choice": choice, "confidence": 0.9,
                            "probabilities": probabilities}
        return {"model": "fixture-only", "answers": answers,
                "usage": {"input_tokens": 7, "output_tokens": 2}}


class RequirementReviewTests(unittest.IsolatedAsyncioTestCase):
    REQUIREMENTS = ["CLI печатает отчёт", "Тесты проходят"]

    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.session = Session.create(Path(self.temporary.name) / "sessions")
        self.session.judge = GapJudge()
        self.written = []

        def change(workspace):
            self.written.append(True)
            (workspace / ("step-%s.txt" % len(self.written))).write_text("работа", encoding="utf-8")

        self.session.runner = QuietRunner(action=change)

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def test_each_approved_requirement_becomes_its_own_question(self):
        await self.session.run_turn("Сделай задачу.", requirements=self.REQUIREMENTS)
        review = next(keys for keys in self.session.judge.asked if "next_action" in keys)
        self.assertIn(requirement_key(0), review)
        self.assertIn(requirement_key(1), review)
        self.assertIn("addresses_request", review)

    async def test_the_unmet_requirement_reaches_the_next_attempt_by_name(self):
        result = await self.session.run_turn("Сделай задачу.", requirements=self.REQUIREMENTS)
        self.assertEqual(result["reason"], "iteration_limit_or_no_progress")
        self.assertEqual([gap["requirement"] for gap in result["open_requirements"]],
                         ["CLI печатает отчёт"])
        second = json.loads(self.session.runner.calls[1]["prompt"].split("\n\n", 1)[1])
        self.assertEqual(second["open_requirements"][0]["requirement"], "CLI печатает отчёт")
        self.assertEqual(second["open_requirements"][0]["closed_noul"], 0.1)
        first = json.loads(self.session.runner.calls[0]["prompt"].split("\n\n", 1)[1])
        self.assertEqual(first["open_requirements"], [])  # Nothing is open before the first review.

    async def test_open_requirements_are_recorded_with_the_decision(self):
        await self.session.run_turn("Сделай задачу.", requirements=self.REQUIREMENTS)
        decisions = [e["data"] for e in self.session.events() if e["type"] == "decision"]
        self.assertTrue(all(d["open_requirements"] for d in decisions))
        self.assertEqual(json.loads((self.session.directory / "turn-001" / "request.json").read_text())
                         ["requirements"], self.REQUIREMENTS)

    async def test_requirements_are_bounded_in_count_and_length_before_they_travel(self):
        from jev_agent.core import MAX_REQUIREMENTS, valid_requirements
        bounded = valid_requirements(["x" * 900] + ["пункт %s" % i for i in range(20)] + ["", "   ", None])
        self.assertEqual(len(bounded), MAX_REQUIREMENTS)
        self.assertLessEqual(max(len(item) for item in bounded), 300)

    async def test_a_turn_without_a_plan_asks_exactly_the_questions_it_did_before(self):
        await self.session.run_turn("Просто ответь.")
        review = next(keys for keys in self.session.judge.asked if "next_action" in keys)
        self.assertEqual(review, ["addresses_request", "next_action"])


class SessionDecisionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.session = Session.create(self.base / "sessions")
        self.session.judge = RoutingJudge()
        self.session.runner = QuietRunner()

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def test_lost_review_keeps_the_work_and_refuses_acceptance(self):
        self.session.checks = [{"id": "ok", "title": "Passes", "argv": [sys.executable, "-c", "pass"],
                                "origin": "registered"}]
        result = await self.session.run_turn("Создай инструмент.")
        self.assertEqual((result["status"], result["reason"]), ("needs_input", "judge_unavailable"))
        self.assertIn("Готово", result["summary"])  # The worker's answer survives the outage.
        self.assertEqual(len(self.session.runner.calls), 1)
        self.assertFalse(result["meters"]["usage_complete"])
        notes = [e for e in self.session.events()
                 if e["type"] == "message" and e["data"].get("role") == "policy"]
        self.assertTrue(any("no acceptance given" in e["data"]["text"] for e in notes))

    async def test_every_decision_records_its_inputs_policy_and_verdict(self):
        self.session.judge = RoutingJudge(fail_on=None)
        result = await self.session.run_turn("Создай инструмент.")
        self.assertEqual(result["policy"], {"version": POLICY_VERSION, "thresholds": thresholds()})
        persisted = json.loads((self.session.directory / "turn-001" / "result.json").read_text())
        self.assertEqual(persisted["policy"]["version"], POLICY_VERSION)
        decisions = [e for e in self.session.events() if e["type"] == "decision"]
        self.assertEqual(len(decisions), 1)
        data = decisions[0]["data"]
        self.assertEqual(data["inputs"]["attempt"], 1)
        self.assertEqual(data["inputs"]["judge_state"], "applied")
        self.assertEqual(data["verdict"]["status"], result["status"])
        self.assertEqual(data["thresholds"], thresholds())

    async def test_jev_events_are_stamped_with_the_attempt_they_belong_to(self):
        calls = []
        def change(workspace):
            calls.append(True)
            (workspace / "value.txt").write_text("fixed" if len(calls) > 1 else "broken")
        self.session.runner = QuietRunner(action=change)
        self.session.checks = [{"id": "value", "title": "value", "argv": [
            sys.executable, "-c", "from pathlib import Path; assert Path('value.txt').read_text() == 'fixed'"],
            "origin": "registered"}]
        self.session.judge = RoutingJudge(fail_on=None)
        result = await self.session.run_turn("Почини значение.")
        self.assertEqual(result["status"], "accepted")
        stamps = {(e["data"]["purpose"], e["data"]["attempt"])
                  for e in self.session.events() if e["type"] == "jev"}
        self.assertIn(("route", 0), stamps)  # Routing happens before any attempt.
        self.assertIn(("review", 1), stamps)
        self.assertIn(("review", 2), stamps)

    async def test_replay_reproduces_every_recorded_decision_without_a_model(self):
        self.session.judge = RoutingJudge(fail_on=None)
        await self.session.run_turn("Создай инструмент.")
        recorded = read_decisions(self.session.directory)
        self.assertTrue(recorded)
        report = replay_session(self.session.directory)
        self.assertEqual(report["mismatches"], 0)
        self.assertEqual(report["reproduced"], report["decisions"])
        self.assertEqual(report["changed_by_current_policy"], 0)
        self.assertTrue(all(turn["reproduced"] for turn in report["turns"]))
        self.assertEqual(self.session.judge.purposes.count("review"), 1)  # Replay asked nothing.

    async def test_replay_reports_a_verdict_that_todays_policy_would_change(self):
        self.session.judge = RoutingJudge(fail_on=None)
        await self.session.run_turn("Создай инструмент.")
        path = self.session.directory / "events.jsonl"
        lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("type") == "decision":
                # Recorded under a lax correspondence bar, which today is stricter.
                event["data"]["inputs"]["review"] = review("finish", 1.0, addresses=0.2)
                event["data"]["verdict"] = dict(event["data"]["verdict"], status="ready", outcome="return")
                event["data"]["thresholds"] = dict(event["data"]["thresholds"],
                                                   addresses_request_min_noul=0.1)
            lines.append(json.dumps(event, ensure_ascii=False))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = replay_session(self.session.directory)
        # The verdict still follows from its own inputs under its own thresholds,
        # so this is drift, not a regression - replay keeps the two apart.
        self.assertEqual(report["mismatches"], 0)
        self.assertEqual(report["changed_by_current_policy"], 1)
        drift = report["turns"][0]["policy_drift"]
        self.assertEqual(drift["reason"]["recorded"], "response_prepared_without_independent_acceptance")
        self.assertEqual(drift["reason"]["recomputed"], "uncertain_request_correspondence")

    async def test_replay_survives_a_truncated_journal_and_a_session_without_decisions(self):
        with (self.session.directory / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write('{"seq": 99, "type": "decision"')  # Interrupted final write.
        self.assertEqual(replay_session(self.session.directory)["decisions"], 0)
        with self.assertRaises(ValueError):
            replay_session(self.base / "nowhere")

    async def test_cli_replay_reads_the_journal_and_reports_through_its_exit_code(self):
        self.session.judge = RoutingJudge(fail_on=None)
        await self.session.run_turn("Создай инструмент.")
        sessions = self.session.directory.parent
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--replay", self.session.id, "--sessions", str(sessions)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["mismatches"], 0)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--replay", "missing-session", "--sessions", str(sessions)]), 2)

    async def test_cli_replay_refuses_to_combine_with_running_a_turn(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["--replay", "last", "--run", "do something", "--sessions", str(self.base)])


if __name__ == "__main__":
    unittest.main()
