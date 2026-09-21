"""The demo path: a real turn whose two network edges answer from the schema."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jev-harness-lab"))
from judge import validate_response  # noqa: E402  (the lab validator the agent already uses)

from jev_agent.cli import main  # noqa: E402
from jev_agent.core import Session  # noqa: E402
from jev_agent.demo import SYNTHETIC_MODEL, DemoJudge, DemoWorker, answer_question, synthesize  # noqa: E402
from jev_agent.intake import INTAKE_SCHEMA, validate_response as validate_intake  # noqa: E402


QUESTIONS = {
    "route": {"type": "choice", "instructions": "Pick a mode.",
              "criteria": {"implement": "change files", "inspect": "read files", "answer": "explain"}},
    "addresses_request": {"type": "noul", "instructions": "Does it address the request?"},
    "severity": {"type": "score", "instructions": "How severe?",
                 "criteria": ["none", "minor", "moderate", "serious"]},
}


class SyntheticAnswerTests(unittest.TestCase):
    def test_answers_satisfy_the_same_validator_as_live_responses(self):
        response = {"model": SYNTHETIC_MODEL, "usage": {"input_tokens": 0, "output_tokens": 0},
                    "answers": {key: answer_question(key, question, {"user_request": "демо"})
                                for key, question in QUESTIONS.items()}}
        validate_response(response, QUESTIONS)  # Raises JudgeError if anything is malformed.

    def test_a_choice_prefers_the_documented_option_and_stays_its_own_argmax(self):
        answer = answer_question("route", QUESTIONS["route"], {})
        self.assertEqual(answer["choice"], "implement")
        self.assertEqual(max(answer["probabilities"], key=answer["probabilities"].get), "implement")
        self.assertAlmostEqual(sum(answer["probabilities"].values()), 1.0, places=6)

    def test_an_unlisted_choice_falls_back_to_the_first_registered_option(self):
        question = {"type": "choice", "instructions": "", "criteria": {"alpha": "a", "beta": "b"}}
        self.assertEqual(answer_question("whatever", question, {})["choice"], "alpha")

    def test_a_score_agrees_with_its_own_weighted_position_and_carries_a_legend(self):
        answer = answer_question("severity", QUESTIONS["severity"], {"case": 3})
        mean = sum(int(k) * v for k, v in answer["probabilities"].items())
        self.assertAlmostEqual(mean, answer["score"], places=3)
        self.assertEqual(set(answer["legend"]), {"0", "1", "2", "3"})
        self.assertEqual(answer["legend"]["2"], "moderate")

    def test_the_same_request_always_produces_the_same_answer(self):
        first = answer_question("relevance", {"type": "noul", "instructions": ""}, {"path": "a.py"})
        second = answer_question("relevance", {"type": "noul", "instructions": ""}, {"path": "a.py"})
        other = answer_question("relevance", {"type": "noul", "instructions": ""}, {"path": "b.py"})
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)  # Ranking stays visible across candidates.

    def test_correspondence_is_answered_high_so_a_demo_turn_reaches_its_verdict(self):
        self.assertGreaterEqual(answer_question("addresses_request", QUESTIONS["addresses_request"], {})["noul"], 0.5)


class SchemaSynthesisTests(unittest.TestCase):
    def test_an_object_carries_exactly_the_keys_its_schema_requires(self):
        # Shape only: the intake contract adds rules a JSON Schema cannot express
        # (snake_case ids, distinct labels), so the worker writes that branch out.
        value = synthesize(INTAKE_SCHEMA)
        self.assertEqual(set(value), set(INTAKE_SCHEMA["required"]))
        self.assertIn(value["kind"], INTAKE_SCHEMA["properties"]["kind"]["enum"])

    def test_arrays_respect_their_own_bounds(self):
        self.assertEqual(len(synthesize({"type": "array", "minItems": 2, "maxItems": 3,
                                          "items": {"type": "string", "maxLength": 20}})), 2)
        self.assertEqual(len(synthesize({"type": "array", "maxItems": 3,
                                          "items": {"type": "string", "maxLength": 20}})), 1)

    def test_strings_never_exceed_their_declared_limit(self):
        self.assertLessEqual(len(synthesize({"type": "string", "maxLength": 6}, "title")), 6)

    def test_nullable_branches_choose_the_described_shape(self):
        value = synthesize({"anyOf": [{"type": "object", "properties": {"a": {"type": "string"}},
                                       "required": ["a"]}, {"type": "null"}]})
        self.assertEqual(set(value), {"a"})


class DemoWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name) / "workspace"
        self.workspace.mkdir()
        self.directory = Path(self.temporary.name) / "worker"
        self.worker = DemoWorker()

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def _run(self, **kwargs):
        import asyncio
        return await self.worker.run("prompt", self.workspace, self.directory,
                                     lambda *a, **k: None, asyncio.Event(), **kwargs)

    async def test_a_readonly_turn_writes_nothing_into_the_workspace(self):
        await self._run(readonly=True)
        self.assertEqual(list(self.workspace.iterdir()), [])

    async def test_a_writing_turn_creates_runnable_files_and_repeats_without_duplicating(self):
        await self._run()
        names = sorted(p.name for p in self.workspace.iterdir())
        self.assertEqual(names, ["demo_tool.py", "test_demo_tool.py"])
        second = await self._run()
        self.assertEqual(sorted(p.name for p in self.workspace.iterdir()), names)
        self.assertIn("Файлы", second["text"] + " ")

    async def test_artifacts_match_the_shape_a_real_worker_leaves_behind(self):
        await self._run()
        for name in ("prompt.txt", "stderr.txt", "events.jsonl", "final.txt"):
            self.assertTrue((self.directory / name).is_file(), name)

    async def test_a_guided_round_asks_first_and_proposes_a_plan_afterwards(self):
        first = json.loads((await self._run(schema=INTAKE_SCHEMA))["text"])
        second = json.loads((await self._run(schema=INTAKE_SCHEMA))["text"])
        self.assertEqual(first["kind"], "questions")
        self.assertIsNone(first["plan"])
        self.assertEqual(second["kind"], "plan")
        self.assertEqual(second["questions"], [])
        for payload in (first, second):
            validate_intake(payload)


class DemoSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)

    async def asyncTearDown(self):
        self.temporary.cleanup()

    async def test_a_full_turn_runs_with_no_codex_and_no_key(self):
        session = Session.create(self.base / "sessions").use_demo()
        self.assertTrue(session.status()["demo"])
        result = await session.run_turn("Сделай утилиту и тест.")
        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["demo"])
        self.assertIsInstance(session.runner, DemoWorker)
        self.assertIsInstance(session.judge, DemoJudge)
        # The checks stage executed real files the demo worker wrote.
        report = json.loads((session.directory / "turn-001" / "attempt-01-checks.json").read_text())
        self.assertEqual((report["passed"], report["total"]), (1, 1))
        self.assertEqual(report["items"][0]["origin"], "worker_generated")

    async def test_every_synthetic_judgement_is_labelled_at_the_source(self):
        session = Session.create(self.base / "sessions").use_demo()
        await session.run_turn("Сделай утилиту и тест.")
        judgements = [e["data"] for e in session.events() if e["type"] == "jev"]
        self.assertTrue(judgements)
        self.assertTrue(all(j["synthetic"] for j in judgements))
        self.assertTrue(all(j["model"] == SYNTHETIC_MODEL for j in judgements))
        self.assertTrue(all(j["usage"] == {"input_tokens": 0, "output_tokens": 0} for j in judgements))

    async def test_a_confident_demo_judgement_cannot_pass_a_failing_contract(self):
        session = Session.create(self.base / "sessions").use_demo()
        session.checks = [{"id": "contract", "title": "Contract", "origin": "registered",
                           "argv": [sys.executable, "-c", "raise SystemExit(1)"]}]
        result = await session.run_turn("Почини проект.")
        self.assertEqual((result["status"], result["reason"]),
                         ("stopped", "checks_failed_or_no_progress"))


class DemoCommandTests(unittest.TestCase):
    """The CLI runs its own event loop, so these stay outside an async case."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def test_cli_refuses_to_point_the_demo_worker_at_a_real_project(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(["--demo", "--project", str(self.base), "--sessions", str(self.base / "s")])

    def test_cli_runs_a_demo_turn_without_touching_the_local_key_file(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--demo", "--sessions", str(self.base / "sessions"),
                         "--run", "Сделай утилиту и тест."])
        self.assertEqual(code, 0)
        ends = [json.loads(line) for line in output.getvalue().splitlines()
                if json.loads(line).get("type") == "end"]
        self.assertEqual(ends[-1]["data"]["status"], "ready")
        self.assertTrue(ends[-1]["data"]["demo"])


if __name__ == "__main__":
    unittest.main()
