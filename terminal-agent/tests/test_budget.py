"""What a decision is allowed to cost: bounded dossiers, full evidence on disk."""
import json
from pathlib import Path
import tempfile
import unittest

from jev_agent.core import (CLAIM_HEAD, CLAIM_TAIL, MAX_FAILURES_SHOWN, MAX_WORKSPACE_ENTRIES,
                            REQUEST_HEAD, REQUEST_TAIL, Session, checks_digest, clip,
                            workspace_outline)


class ClipTests(unittest.TestCase):
    def test_short_text_is_returned_untouched(self):
        self.assertEqual(clip("короткий", 100, 50), "короткий")
        self.assertEqual(clip("", 10, 5), "")
        self.assertEqual(clip(None, 10, 5), "")

    def test_both_ends_survive_and_the_omission_is_stated(self):
        text = "НАЧАЛО" + "x" * 5000 + "КОНЕЦ"
        clipped = clip(text, 100, 50)
        self.assertTrue(clipped.startswith("НАЧАЛО"))
        self.assertTrue(clipped.endswith("КОНЕЦ"))
        self.assertIn("пропущено %s символов" % (len(text) - 150), clipped)
        self.assertLess(len(clipped), 300)

    def test_a_zero_tail_keeps_only_the_opening(self):
        clipped = clip("НАЧАЛО" + "x" * 900, 20, 0)
        self.assertTrue(clipped.startswith("НАЧАЛО"))
        self.assertIn("пропущено", clipped)


class ChecksDigestTests(unittest.TestCase):
    def _report(self, failures, passes=1):
        items = [{"id": "ok-%s" % i, "passed": True, "exit_code": 0, "output": "fine"}
                 for i in range(passes)]
        items += [{"id": "bad-%s" % i, "passed": False, "exit_code": 1, "output": "НАЧАЛО" + "y" * 4000 + "КОНЕЦ"}
                  for i in range(failures)]
        return {"items": items, "passed": passes, "total": len(items), "fresh": True,
                "registered": True, "stage": "attempt-01"}

    def test_counts_are_complete_while_output_is_only_kept_for_failures(self):
        digest = checks_digest(self._report(failures=1))
        self.assertEqual((digest["passed"], digest["total"], digest["failed"]), (1, 2, 1))
        self.assertEqual(len(digest["failures"]), 1)
        self.assertEqual(digest["failures"][0]["id"], "bad-0")
        self.assertTrue(digest["failures"][0]["output"].startswith("НАЧАЛО"))
        self.assertTrue(digest["failures"][0]["output"].endswith("КОНЕЦ"))

    def test_the_number_of_failures_shown_is_bounded_but_counted_in_full(self):
        digest = checks_digest(self._report(failures=7))
        self.assertEqual(digest["failed"], 7)
        self.assertEqual(len(digest["failures"]), MAX_FAILURES_SHOWN)

    def test_an_absent_report_stays_absent_and_a_partial_one_does_not_raise(self):
        self.assertIsNone(checks_digest(None))
        partial = checks_digest({"items": [{"id": "x", "passed": False}], "fresh": True})
        self.assertEqual((partial["total"], partial["failed"], partial["passed"]), (1, 1, 0))
        self.assertEqual(partial["failures"][0]["output"], "")


class WorkspaceOutlineTests(unittest.TestCase):
    def test_directories_come_first_and_the_list_is_bounded(self):
        files = ["src/app.py", "src/util.py", "tests/test_app.py"]
        files += ["file-%02d.txt" % i for i in range(40)]
        outline = workspace_outline(files)
        self.assertEqual(outline[:2], ["src", "tests"])
        self.assertEqual(len(outline), MAX_WORKSPACE_ENTRIES)

    def test_an_empty_workspace_has_an_empty_outline(self):
        self.assertEqual(workspace_outline([]), [])


class RecordingJudge:
    """Captures exactly what a decision was asked to read."""
    def __init__(self):
        self.states = {}

    async def ask(self, state, questions, directory, emit, cancel_event):
        purpose = "review" if "next_action" in questions else "route" if "route" in questions else "other"
        self.states.setdefault(purpose, []).append(state)
        answers = {}
        for key, question in questions.items():
            if question["type"] == "noul":
                answers[key] = {"type": "noul", "noul": 1.0}
            else:
                choice = "answer" if key == "route" else "finish"
                choice = choice if choice in question["criteria"] else list(question["criteria"])[0]
                answers[key] = {"type": "choice", "choice": choice, "confidence": 1.0,
                                "probabilities": {k: float(k == choice) for k in question["criteria"]}}
        return {"model": "fixture-only", "answers": answers,
                "usage": {"input_tokens": 3, "output_tokens": 1}}


class QuietRunner:
    def __init__(self):
        self.calls = []

    async def run(self, prompt, workspace, directory, emit, cancel_event, readonly=False, schema=None):
        self.calls.append(prompt)
        return {"text": "Разобрал проект.", "usage": {"input_tokens": 1, "output_tokens": 1},
                "completed": True}


class DossierTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.session = Session.create(Path(self.temporary.name) / "sessions")
        self.session.judge = RecordingJudge()
        self.session.runner = QuietRunner()

    async def asyncTearDown(self):
        self.temporary.cleanup()

    def _size(self, state):
        return len(json.dumps(state, ensure_ascii=False).encode("utf-8"))

    async def test_the_routing_dossier_does_not_grow_with_the_session(self):
        await self.session.run_turn("Опиши проект.")
        first = self._size(self.session.judge.states["route"][0])
        # A long conversation used to travel in full: six entries of up to 16000
        # characters each reached the model that only chooses a mode.
        self.session.history = [{"role": "assistant", "text": "Ш" * 16000} for _ in range(6)]
        await self.session.run_turn("Опиши проект ещё раз.")
        second = self.session.judge.states["route"][1]
        self.assertLess(self._size(second), 8000)
        self.assertLess(self._size(second) - first, 2000)
        self.assertNotIn("Ш" * 1000, json.dumps(second, ensure_ascii=False))

    async def test_the_routing_dossier_describes_the_workspace_without_listing_it(self):
        for index in range(60):
            (self.session.workspace / ("file-%02d.txt" % index)).write_text("x", encoding="utf-8")
        (self.session.workspace / "src").mkdir()
        (self.session.workspace / "src" / "app.py").write_text("x", encoding="utf-8")
        await self.session.run_turn("Опиши проект.")
        state = self.session.judge.states["route"][0]
        self.assertNotIn("workspace_files", state)
        self.assertEqual(state["workspace"]["files"], 61)
        self.assertLessEqual(len(state["workspace"]["entries"]), MAX_WORKSPACE_ENTRIES)
        # Directories carry the signal; a flat pile of files must not crowd them out.
        self.assertEqual(state["workspace"]["entries"][0], "src")

    async def test_a_long_request_keeps_both_of_its_ends(self):
        prompt = "СНАЧАЛА задача." + "п" * 9000 + " А в конце ВОПРОС?"
        await self.session.run_turn(prompt)
        asked = self.session.judge.states["route"][0]["user_request"]
        self.assertTrue(asked.startswith("СНАЧАЛА задача."))
        self.assertTrue(asked.endswith("ВОПРОС?"))
        self.assertLess(len(asked), REQUEST_HEAD + REQUEST_TAIL + 200)

    async def test_the_review_reads_a_digest_while_the_worker_keeps_the_evidence(self):
        self.session.judge.states.clear()
        await self.session.run_turn("Опиши проект.")
        review = self.session.judge.states["review"][0]
        self.assertLessEqual(len(review["worker_claim"]), CLAIM_HEAD + CLAIM_TAIL + 200)
        self.assertIn("changed_file_count", review)
        # A read-only turn runs no checks; the field is present and explicitly empty.
        self.assertIsNone(review["observed_checks"])


if __name__ == "__main__":
    unittest.main()
