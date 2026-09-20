import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jev_agent.missions import MISSION_ROOT, prepare_mission


class LoglabMissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="jev-mission-test-")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "workspace"
        self.mission = prepare_mission("loglab", self.project)

    def run_check(self, identity):
        check = next(check for check in self.mission["checks"] if check["id"] == identity)
        result = subprocess.run(check["argv"], capture_output=True, text=True, timeout=15)
        return result.returncode, json.loads(result.stdout)

    def test_mission_contract_is_external_and_complete(self):
        self.assertEqual(6, len(self.mission["checks"]))
        self.assertIn("README.md", self.mission["prompt"])
        self.assertEqual([], self.mission["protected"])
        self.assertTrue((self.project / "loglab_core" / "pipeline.py").is_file())
        self.assertTrue((self.project / "fixtures" / "incident.jsonl").is_file())
        self.assertFalse((self.project / "oracle.py").exists())
        for check in self.mission["checks"]:
            self.assertEqual((MISSION_ROOT / "loglab" / "oracle.py").resolve(), Path(check["argv"][2]).resolve())

    def test_never_overwrites_user_files(self):
        (self.project / "sentinel.txt").write_text("keep me")
        with self.assertRaisesRegex(ValueError, "empty"):
            prepare_mission("loglab", self.project)
        self.assertEqual("keep me", (self.project / "sentinel.txt").read_text())

    def test_unknown_mission_is_rejected_without_creating_workspace(self):
        target = Path(self.temporary.name) / "unknown"
        with self.assertRaisesRegex(ValueError, "Unknown mission"):
            prepare_mission("missing", target)
        self.assertFalse(target.exists())

    def test_rejects_workspace_symlink(self):
        link = Path(self.temporary.name) / "link"
        link.symlink_to(self.project, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            prepare_mission("loglab", link)

    def test_four_seeded_defects_are_detected(self):
        for identity in ("timestamps", "duplicates", "malformed", "severity"):
            with self.subTest(check=identity):
                code, result = self.run_check(identity)
                self.assertEqual(1, code, result)
                self.assertIs(False, result["passed"])
                self.assertEqual(identity, result["check_id"])
                self.assertTrue(result["detail"])

    def test_report_artifacts_already_work_for_clean_input(self):
        code, result = self.run_check("artifacts")
        self.assertEqual(0, code, result)
        self.assertIs(True, result["passed"])

    def test_combined_incident_fails_until_repaired(self):
        code, result = self.run_check("combined")
        self.assertEqual(1, code, result)
        self.assertIs(False, result["passed"])

    def test_unknown_check_is_a_tool_error(self):
        result = subprocess.run([sys.executable, str(MISSION_ROOT / "loglab" / "oracle.py"),
                                 "--check", "not-registered", "--project", str(self.project)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(2, result.returncode)
        self.assertIs(False, json.loads(result.stdout)["passed"])


if __name__ == "__main__":
    unittest.main()
