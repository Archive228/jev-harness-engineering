"""Local navigation never runs a worker and previews stay inside the workspace."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jev_agent.catalog import (MAX_DRAFT_CHARS, MAX_TEXT_BYTES, export_session,
                               list_artifacts, list_sessions, load_draft,
                               read_artifact, save_draft)
from jev_agent.cli import main
from jev_agent.core import Session


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.session = Session.create(self.base / "sessions")

    def test_saved_session_title_and_corrupt_entry(self):
        self.session.history = [{"role": "user", "text": "Первый запрос\nна двух строках"}]
        self.session.save()
        bad = self.base / "sessions" / "bad"
        bad.mkdir()
        (bad / "session.json").write_text("{broken")
        (self.base / "sessions" / "link").symlink_to(self.session.directory)
        rows = list_sessions(self.base / "sessions")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], self.session.id)
        self.assertEqual(rows[0]["title"], "Первый запрос на двух строках")
        self.assertEqual(rows[0]["turns"], 1)

    def test_draft_preserves_full_multiline_and_private_permissions(self):
        text = "Начало\n\n" + "строка\n" * 100
        save_draft(self.session, text)
        self.assertEqual(load_draft(self.session), text)
        self.assertEqual((self.session.directory / "draft.txt").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            save_draft(self.session, "a" * (MAX_DRAFT_CHARS + 1))
        self.assertEqual(load_draft(self.session), text)

    def test_draft_symlink_is_not_read_or_written_through(self):
        outside = self.base / "outside.txt"
        outside.write_text("keep")
        (self.session.directory / "draft.txt").symlink_to(outside)
        self.assertEqual(load_draft(self.session), "")
        save_draft(self.session, "new")
        self.assertEqual(outside.read_text(), "keep")
        self.assertFalse((self.session.directory / "draft.txt").is_symlink())

    def test_traversal_secret_and_symlink_previews_are_rejected(self):
        outside = self.base / "outside.txt"
        outside.write_text("secret")
        (self.session.workspace / "linked.py").symlink_to(outside)
        for path in ("../outside.txt", str(outside), "linked.py", ".env.live",
                     "nested/credentials.json", ".ssh/config", "key.pem", "auth.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                read_artifact(self.session, path)

    def test_binary_and_long_unicode_preview(self):
        (self.session.workspace / "binary").write_bytes(b"a\0b")
        self.assertEqual(read_artifact(self.session, "binary")["text"], "")
        (self.session.workspace / "large.py").write_text("x" * (MAX_TEXT_BYTES - 1) + "Ж" * 10)
        result = read_artifact(self.session, "large.py")
        self.assertTrue(result["truncated"])
        self.assertTrue(result["text"].startswith("x" * 100))
        self.assertIn("64", result["notice"])

    def test_file_swap_to_symlink_cannot_escape_preview(self):
        file = self.session.workspace / "a.py"
        file.write_text("safe")
        outside = self.base / "outside.txt"
        outside.write_text("outside-canary")
        original_open = os.open

        def swapped(name, flags, *args, **kwargs):
            if name == "a.py":
                file.unlink()
                file.symlink_to(outside)
            return original_open(name, flags, *args, **kwargs)

        with patch("jev_agent.catalog.os.open", side_effect=swapped):
            result = read_artifact(self.session, "a.py")
        self.assertEqual(result["text"], "")
        self.assertNotIn("outside-canary", str(result))
        self.assertIn("unavailable", result["notice"])

    def test_latest_captured_diff_is_available_even_for_deleted_file(self):
        for number, diff in ((1, "old"), (2, "--- a.py\n+++ /dev/null\n-x")):
            turn = self.session.directory / ("turn-%03d" % number)
            turn.mkdir()
            (turn / "attempt-01-diffs.json").write_text(json.dumps({
                "a.py": {"status": "deleted", "diff": diff, "truncated": False}}))
        result = read_artifact(self.session, "a.py")
        self.assertIn("/dev/null", result["diff"])
        self.assertIn("deleted", result["notice"])
        self.assertIn({"path": "a.py", "status": "deleted"}, list_artifacts(self.session))

    def test_file_listing_skips_private_and_generated_directories(self):
        for name in ("app.py", ".env", "auth.json", "public.md"):
            (self.session.workspace / name).write_text("text")
        generated = self.session.workspace / "node_modules"
        generated.mkdir()
        (generated / "noise.js").write_text("noise")
        paths = {row["path"] for row in list_artifacts(self.session)}
        self.assertEqual(paths, {"app.py", "public.md"})

    def test_export_retains_actual_events_and_redacts_known_key_patterns(self):
        self.session.history = [{"role": "user", "text": "line 1\nline 2\n```py\na=1\n```"}]
        event = {"seq": 1, "type": "tool", "data": {
            "command": "echo test", "output": "apikey_fixture_secret_for_test", "exit_code": 7}}
        with patch.object(self.session, "events", return_value=[event]):
            exported = export_session(self.session).read_text()
        self.assertIn("line 1\nline 2", exported)
        self.assertIn("````text", exported)
        self.assertIn('"exit_code": 7', exported)
        self.assertNotIn("apikey_fixture", exported)

    def test_list_cli_does_not_create_a_session_or_read_key(self):
        empty = self.base / "empty"
        with patch("jev_agent.cli.load_local_key") as key, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--sessions", str(empty), "--list"]), 0)
        key.assert_not_called()
        self.assertEqual(json.loads(output.getvalue()), [])
        self.assertFalse(empty.exists())

    def test_export_cli_never_calls_a_model_or_reads_key(self):
        with patch("jev_agent.cli.load_local_key") as key, \
             patch.object(Session, "run_turn") as run, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--sessions", str(self.base / "sessions"), "--resume", self.session.id, "--export"]), 0)
        key.assert_not_called()
        run.assert_not_called()
        self.assertTrue(Path(output.getvalue().strip()).is_file())

    def test_export_requires_existing_session(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["--export"])


if __name__ == "__main__":
    unittest.main()
