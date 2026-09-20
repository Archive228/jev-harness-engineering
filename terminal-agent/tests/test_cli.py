"""Reader-facing resume commands use real saved sessions without model calls."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest

from jev_agent.cli import main
from jev_agent.core import Session


class ResumePathTests(unittest.TestCase):
    def test_relative_path_and_session_id_both_export_the_selected_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            session = Session.create(base / "sessions")
            previous = Path.cwd()
            try:
                os.chdir(base)
                for reference in ("sessions/" + session.id, session.id):
                    with self.subTest(reference=reference), contextlib.redirect_stdout(io.StringIO()):
                        result = main(["--sessions", "sessions", "--resume", reference, "--export"])
                    self.assertEqual(result, 0)
                    self.assertTrue((session.directory / "exports/session.md").is_file())
                    self.assertEqual(session.events(), [])
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
