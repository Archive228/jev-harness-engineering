"""The layer around a Jev call: cache, size guard, retries and the breaker."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jev_agent import transport
from jev_agent.runtime import JevJudge, RuntimeFailure


ANSWER = {"model": "jev-1.13.0", "answers": {"route": {"type": "choice", "choice": "answer",
                                                        "confidence": 1.0,
                                                        "probabilities": {"answer": 1.0}}},
          "usage": {"input_tokens": 12, "output_tokens": 3}}
QUESTIONS = {"route": {"type": "choice", "instructions": "Pick.", "criteria": {"answer": "explain"}}}


class IsolatedCache(unittest.TestCase):
    """Never touch the real ~/.jev while testing it."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.previous = {name: os.environ.get(name) for name in ("JEV_CACHE_DIR", "JEV_CACHE")}
        os.environ["JEV_CACHE_DIR"] = str(Path(self.temporary.name) / "jev")
        os.environ.pop("JEV_CACHE", None)
        self.addCleanup(self._restore)

    def _restore(self):
        for name, value in self.previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class KeyAndSizeTests(IsolatedCache):
    def test_identity_follows_the_state_and_the_questions(self):
        base = {"model": "m", "state": {"a": 1}, "questions": QUESTIONS}
        self.assertEqual(transport.request_key(base), transport.request_key(dict(base)))
        self.assertEqual(transport.request_key(base),
                         transport.request_key({"questions": QUESTIONS, "state": {"a": 1}, "model": "m"}))
        self.assertNotEqual(transport.request_key(base),
                            transport.request_key({**base, "state": {"a": 2}}))
        self.assertNotEqual(transport.request_key(base), transport.request_key({**base, "model": "n"}))

    def test_an_impossible_request_is_refused_before_any_process_starts(self):
        small = {"model": "m", "state": {"text": "x"}, "questions": QUESTIONS}
        self.assertLess(transport.check_size(small), transport.MAX_REQUEST_BYTES)
        with self.assertRaises(transport.TransportRefusal) as caught:
            transport.check_size({"model": "m", "questions": QUESTIONS,
                                  "state": {"text": "x" * (transport.MAX_REQUEST_BYTES + 10)}})
        self.assertIn(str(transport.MAX_REQUEST_BYTES), str(caught.exception))


class CacheTests(IsolatedCache):
    def test_an_answer_comes_back_for_the_same_request(self):
        key = transport.request_key({"model": "m", "state": {}, "questions": QUESTIONS})
        self.assertIsNone(transport.read_cache(key))
        self.assertTrue(transport.write_cache(key, ANSWER))
        self.assertEqual(transport.read_cache(key), ANSWER)

    def test_entries_expire_and_damaged_entries_are_a_miss_not_a_crash(self):
        key = "a" * 64
        transport.write_cache(key, ANSWER, now=1000.0)
        self.assertIsNone(transport.read_cache(key, now=1000.0 + transport.CACHE_TTL_SECONDS + 1))
        self.assertEqual(transport.read_cache(key, now=1000.0), ANSWER)
        (transport.root() / "cache" / (key + ".json")).write_text("{ broken", encoding="utf-8")
        self.assertIsNone(transport.read_cache(key))

    def test_the_cache_holds_request_state_so_it_stays_private(self):
        key = "b" * 64
        transport.write_cache(key, ANSWER)
        self.assertEqual((transport.root() / "cache" / (key + ".json")).stat().st_mode & 0o777, 0o600)
        self.assertEqual((transport.root() / "cache").stat().st_mode & 0o777, 0o700)

    def test_it_can_be_switched_off_entirely(self):
        os.environ["JEV_CACHE"] = "off"
        key = "c" * 64
        self.assertFalse(transport.write_cache(key, ANSWER))
        self.assertIsNone(transport.read_cache(key))


class BreakerTests(IsolatedCache):
    def test_it_opens_only_after_repeated_failures_and_a_success_resets_it(self):
        for _ in range(transport.BREAKER_FAILURES - 1):
            transport.record_failure(now=1000.0)
        self.assertIsNone(transport.breaker_block(now=1000.0))
        transport.record_failure(now=1000.0)
        blocked = transport.breaker_block(now=1000.0)
        self.assertIsNotNone(blocked)
        self.assertIn(str(transport.BREAKER_FAILURES), blocked)
        self.assertIsNone(transport.breaker_block(now=1000.0 + transport.BREAKER_COOLDOWN_SECONDS + 1))
        transport.record_success()
        self.assertIsNone(transport.breaker_block(now=1000.0))

    def test_each_further_failure_waits_longer_up_to_a_ceiling(self):
        opens = [transport.record_failure(now=0.0) for _ in range(9)]
        waits = [value for value in opens if value]
        self.assertEqual(waits[0], transport.BREAKER_COOLDOWN_SECONDS)
        self.assertLess(waits[0], waits[1])
        self.assertLessEqual(max(waits), transport.MAX_COOLDOWN_SECONDS)

    def test_an_unreadable_breaker_file_does_not_block_the_agent(self):
        transport._prepare(transport.root())
        (transport.root() / "breaker.json").write_text("not json", encoding="utf-8")
        self.assertIsNone(transport.breaker_block())


class ClassificationTests(unittest.TestCase):
    def test_transport_faults_are_retried_and_answered_errors_are_not(self):
        for message in ("Jev: HTTP 429", "Jev: HTTP 503", "Jev: HTTP 529",
                        "Jev: API transport/JSON failure: URLError",
                        "Jev: API transport/JSON failure: TimeoutError"):
            self.assertTrue(transport.retryable(message), message)
        for message in ("Jev: HTTP 401", "Jev: HTTP 400",
                        "Jev: API transport/JSON failure: JSONDecodeError",
                        "Jev: Choice outside registered options",
                        "Jev: TYPESAFE_API_KEY is not set.", ""):
            self.assertFalse(transport.retryable(message), message)


class JudgeTransportTests(IsolatedCache, unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        IsolatedCache.setUp(self)
        self.directory = Path(self.temporary.name) / "jev-01"
        self.spawns = []

    def _process(self, exit_code=0, stderr="", codes=None):
        """Stand in for the child process, recording every spawn."""
        sequence = list(codes or [])

        async def fake(argv, **kwargs):
            self.spawns.append(argv)
            code, text = (sequence.pop(0) if sequence else (exit_code, stderr))
            if not code:
                Path(argv[3]).write_text(json.dumps(ANSWER), encoding="utf-8")
            return {"exit_code": code, "stderr": text, "stdout": "", "elapsed_ms": 4.0}
        return fake

    async def test_a_successful_call_is_cached_and_the_next_one_spawns_nothing(self):
        with patch("jev_agent.runtime.process", self._process()):
            first = await JevJudge().ask({"q": 1}, QUESTIONS, self.directory,
                                         lambda *a, **k: None, asyncio.Event())
            self.assertEqual(first["answers"], ANSWER["answers"])
            self.assertNotIn("_cached", first)
            second = await JevJudge().ask({"q": 1}, QUESTIONS, self.directory / "again",
                                          lambda *a, **k: None, asyncio.Event())
        self.assertTrue(second["_cached"])
        self.assertEqual(second["usage"], ANSWER["usage"])
        self.assertEqual(len(self.spawns), 1)
        self.assertTrue((self.directory / "again" / "response.json").is_file())

    async def test_a_different_state_is_a_different_call(self):
        with patch("jev_agent.runtime.process", self._process()):
            await JevJudge().ask({"q": 1}, QUESTIONS, self.directory, lambda *a, **k: None, asyncio.Event())
            await JevJudge().ask({"q": 2}, QUESTIONS, self.directory / "b", lambda *a, **k: None, asyncio.Event())
        self.assertEqual(len(self.spawns), 2)

    async def test_a_transport_fault_is_retried_and_reported_while_waiting(self):
        notices = []
        with patch("jev_agent.runtime.process",
                   self._process(codes=[(1, "Jev: HTTP 429"), (0, "")])):
            with patch("jev_agent.transport.RETRY_DELAYS", (0.01, 0.01)):
                response = await JevJudge().ask({"q": 3}, QUESTIONS, self.directory,
                                                lambda kind, **data: notices.append((kind, data)),
                                                asyncio.Event())
        self.assertEqual(response["answers"], ANSWER["answers"])
        self.assertEqual(len(self.spawns), 2)
        self.assertTrue(any("429" in data.get("text", "") for _, data in notices))
        self.assertIsNone(transport.breaker_block())  # The eventual success cleared it.

    async def test_an_answered_error_is_not_retried_and_counts_against_the_breaker(self):
        with patch("jev_agent.runtime.process", self._process(exit_code=1, stderr="Jev: HTTP 401")):
            with self.assertRaises(RuntimeFailure) as caught:
                await JevJudge().ask({"q": 4}, QUESTIONS, self.directory,
                                     lambda *a, **k: None, asyncio.Event())
        self.assertIn("401", str(caught.exception))
        self.assertEqual(len(self.spawns), 1)

    async def test_repeated_failures_stop_the_agent_from_calling_at_all(self):
        with patch("jev_agent.runtime.process", self._process(exit_code=1, stderr="Jev: HTTP 401")):
            for index in range(transport.BREAKER_FAILURES):
                with self.assertRaises(RuntimeFailure):
                    await JevJudge().ask({"q": index}, QUESTIONS, self.directory / str(index),
                                         lambda *a, **k: None, asyncio.Event())
            spawned = len(self.spawns)
            with self.assertRaises(RuntimeFailure) as caught:
                await JevJudge().ask({"q": "next"}, QUESTIONS, self.directory / "blocked",
                                     lambda *a, **k: None, asyncio.Event())
        self.assertIn("unavailable", str(caught.exception))
        self.assertEqual(len(self.spawns), spawned)  # Blocked without touching the network.

    async def test_an_oversized_state_is_refused_before_spawning(self):
        with patch("jev_agent.runtime.process", self._process()):
            with self.assertRaises(transport.TransportRefusal):
                await JevJudge().ask({"text": "x" * (transport.MAX_REQUEST_BYTES + 10)}, QUESTIONS,
                                     self.directory, lambda *a, **k: None, asyncio.Event())
        self.assertEqual(self.spawns, [])

    async def test_a_stop_during_backoff_is_honoured(self):
        cancel = asyncio.Event()

        async def fake(argv, **kwargs):
            self.spawns.append(argv)
            cancel.set()  # The user presses stop while the first attempt fails.
            return {"exit_code": 1, "stderr": "Jev: HTTP 429", "stdout": "", "elapsed_ms": 1.0}

        with patch("jev_agent.runtime.process", fake):
            with self.assertRaises(asyncio.CancelledError):
                await JevJudge().ask({"q": 5}, QUESTIONS, self.directory,
                                     lambda *a, **k: None, cancel)
        self.assertEqual(len(self.spawns), 1)


if __name__ == "__main__":
    unittest.main()
