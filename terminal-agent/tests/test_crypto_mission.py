"""The crypto exercise starts broken and its acceptance predates the worker."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from jev_agent.core import Session


class CryptoMissionTests(unittest.TestCase):
    def test_seed_contract_detects_six_defects_and_is_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Session.create(Path(tmp), mission="cryptolab")
            self.assertIn("Decimal", session.example_prompt)
            self.assertEqual(len(session.checks), 1)
            self.assertTrue(any("test_contract.py" in path for path in session.contract_hashes))
            result = subprocess.run(session.checks[0]["argv"], cwd=session.workspace,
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Ran 7 tests", result.stderr)
            self.assertIn("failures=5, errors=1", result.stderr)


if __name__ == "__main__":
    unittest.main()
