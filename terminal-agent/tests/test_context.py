"""Real filesystem evidence, exclusions and budgets; no provider calls."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from jev_agent.context import (MAX_CANDIDATES, MAX_EXCERPT_BYTES, capture_texts,
                               diff_details, read_safe_text, shortlist, tokens)
from jev_agent.core import snapshot


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_russian_and_identifier_tokens_are_supported_without_translation(self):
        self.assertIn("кошельки", tokens("Найди связанные кошельки и eventId"))
        self.assertIn("event", tokens("eventId"))
        self.write("wallets.py", "# связанные кошельки\nvalue = 1\n")
        result = shortlist(self.root, "Найди связанные кошельки")
        self.assertEqual(result["candidates"][0]["path"], "wallets.py")

    def test_attributed_snippet_preserves_real_lines_and_full_file_hash(self):
        source = "first\nsecond\nthird\nneedle target\nfifth\n"
        self.write("app.py", source)
        entry = shortlist(self.root, "needle target")["candidates"][0]
        self.assertEqual(entry["sha256"], hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(entry["start_line"], 1)
        self.assertEqual(entry["end_line"], 5)
        self.assertEqual(entry["excerpt"], source)

    def test_dependencies_hidden_secrets_binary_symlinks_and_ignored_files_are_excluded(self):
        for name in ("node_modules/evil.py", ".private/hidden.py", "credentials.json", "auth.json",
                     "secrets.py", "private_key.txt", "ignored.py", "nested/generated.py"):
            self.write(name, "needle sensitive")
        self.write(".gitignore", "ignored.py\n")
        self.write("nested/.gitignore", "generated.py\n")
        self.write("settings.py", 'API_KEY = "not-for-model"\nneedle = 1\n')
        self.write("null.py", "needle\x00private")
        good = self.write("app.py", "needle public")
        (self.root / "alias.py").symlink_to(good)
        (self.root / "alias-dir").symlink_to(self.root / ".private", target_is_directory=True)
        result = shortlist(self.root, "needle")
        self.assertEqual([c["path"] for c in result["candidates"]], ["app.py"])
        self.assertIsNone(read_safe_text(self.root, "alias.py"))
        self.assertIsNone(read_safe_text(self.root, "alias-dir/hidden.py"))
        self.assertIsNone(read_safe_text(self.root, "../outside.py"))

    def test_candidate_excerpt_read_and_file_budgets_are_hard_limits(self):
        for index in range(15):
            self.write("file-%02d.py" % index, "needle " + "я" * 3000)
        result = shortlist(self.root, "needle")
        self.assertEqual(len(result["candidates"]), MAX_CANDIDATES)
        self.assertTrue(result["partial"])
        for candidate in result["candidates"]:
            self.assertLessEqual(len(candidate["excerpt"].encode()), MAX_EXCERPT_BYTES)
            self.assertTrue(candidate["excerpt_truncated"])
        limited = shortlist(self.root, "needle", max_files=2, max_read_bytes=6500)
        self.assertLessEqual(limited["files_scanned"], 2)
        self.assertLessEqual(limited["bytes_read"], 6500)
        self.assertTrue(limited["partial"])

    def test_rejected_content_counts_toward_read_budget(self):
        for index in range(12):
            self.write("f%02d.py" % index, "needle\0" + "x" * 1000)
        result = shortlist(self.root, "needle", max_read_bytes=2100)
        self.assertEqual(result["candidates"], [])
        self.assertLessEqual(result["bytes_read"], 2100)
        self.assertGreater(result["bytes_read"], 0)

    def test_no_overlap_does_not_invent_relevance(self):
        self.write("alpha.py", "alpha = 123")
        result = shortlist(self.root, "несуществующий термин")
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["no_matches"])

    @unittest.skipUnless(shutil.which("git"), "Git integration boundary requires git")
    def test_workspace_beneath_ignored_outer_repository_keeps_its_own_sources(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write(".gitignore", ".sessions/\n")
        workspace = self.root / ".sessions" / "example" / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "app.py").write_text("needle = 1\n")
        (workspace / "local-only.py").write_text("needle = 2\n")
        (workspace / ".gitignore").write_text("local-only.py\n")
        result = shortlist(workspace, "needle")
        self.assertEqual([c["path"] for c in result["candidates"]], ["app.py"])
        self.assertFalse(result["no_matches"])
        before = snapshot(workspace)
        captured = capture_texts(workspace, before["files"])
        self.assertEqual(set(captured), {"app.py"})
        (workspace / "app.py").write_text("needle = 3\n")
        details = diff_details(workspace, ["app.py"], before, snapshot(workspace), captured)
        self.assertIn("-needle = 1\n+needle = 3", details["app.py"]["diff"])

    @unittest.skipUnless(shutil.which("git"), "Git integration boundary requires git")
    def test_repository_root_still_honors_git_native_excludes(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.write(".git/info/exclude", "native-only.py\n")
        self.write("native-only.py", "needle hidden")
        self.write("app.py", "needle visible")
        result = shortlist(self.root, "needle")
        self.assertEqual([c["path"] for c in result["candidates"]], ["app.py"])

    def test_diff_is_actual_content_with_snapshot_hashes(self):
        self.write("app.py", "value = 1\n")
        self.write("gone.py", "old = True\n")
        before = snapshot(self.root)
        captured = capture_texts(self.root, before["files"])
        self.write("app.py", "value = 2\n")
        (self.root / "gone.py").unlink()
        self.write("new.py", "added = True\n")
        after = snapshot(self.root)
        details = diff_details(self.root, ["app.py", "gone.py", "new.py"], before, after, captured)
        self.assertIn("-value = 1\n+value = 2", details["app.py"]["diff"])
        self.assertEqual(details["app.py"]["before_sha256"], before["files"]["app.py"])
        self.assertEqual(details["app.py"]["after_sha256"], after["files"]["app.py"])
        self.assertEqual(details["gone.py"]["status"], "deleted")
        self.assertEqual(details["new.py"]["status"], "added")

    def test_missing_or_stale_capture_is_explicit_and_not_a_fabricated_diff(self):
        self.write("app.py", "first\n")
        captured = capture_texts(self.root, ["app.py"])
        self.write("app.py", "changed outside capture\n")
        before = snapshot(self.root)
        self.write("app.py", "worker change\n")
        details = diff_details(self.root, ["app.py"], before, snapshot(self.root), captured)
        self.assertEqual(details["app.py"]["diff"], "")
        self.assertTrue(details["app.py"]["truncated"])

    def test_diff_omits_secret_files_and_honors_total_capture_budget(self):
        for index in range(20):
            self.write("f%02d.py" % index, "x" * 50000)
        self.write("credentials.json", '{"secret":"private"}')
        captured = capture_texts(self.root, snapshot(self.root)["files"])
        self.assertLessEqual(len(captured), 10)
        self.assertLessEqual(sum(s["bytes"] for s in captured.values()), 256 * 1024)
        self.assertNotIn("credentials.json", captured)


if __name__ == "__main__":
    unittest.main()
