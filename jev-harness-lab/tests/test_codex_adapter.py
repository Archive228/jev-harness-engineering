import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


PATH = Path(__file__).resolve().parents[1] / "adapters" / "codex_cli.py"
SPEC = importlib.util.spec_from_file_location("codex_adapter", PATH)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


class CodexAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "runs" / "example" / "project"
        self.project.mkdir(parents=True)
        (self.project / "app.py").write_text('fields = ["title"]\n')
        self.request = {"project": str(self.project), "task": "Search title and description", "feedback": {}, "iteration": 1}

    def invoke(self, *, returncode=0, events=None, claim="Changed request fields", mutate=None, raises=None):
        if events is None:
            events = [{"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 3}}]

        def fake_run(argv, **kwargs):
            if raises:
                raise raises
            if claim is not None:
                Path(argv[argv.index("--output-last-message") + 1]).write_text(claim)
            if mutate:
                mutate()
            stdout = events if isinstance(events, str) else "\n".join(json.dumps(event) for event in events)
            return subprocess.CompletedProcess(argv, returncode, stdout, "SECRET PROVIDER STDERR")

        with patch.object(adapter, "LAB_ROOT", self.root), \
                patch.object(adapter.Path, "cwd", return_value=self.project), \
                patch.object(adapter.sys, "argv", [str(PATH)]), \
                patch.object(adapter.sys, "stdin", io.StringIO(json.dumps(self.request))), \
                patch.object(adapter.sys, "stdout", io.StringIO()) as output, \
                patch.object(adapter.sys, "stderr", io.StringIO()) as error, \
                patch.object(adapter, "resolve_binary", return_value="/bin/codex"), \
                patch.dict(adapter.os.environ, {"TYPESAFE_API_KEY": "SECRET JUDGE KEY"}), \
                patch.object(adapter.subprocess, "run", side_effect=fake_run) as run:
            code = adapter.main()
            return code, output.getvalue(), error.getvalue(), run

    def test_live_worker_protocol_with_sandbox_and_default_model(self):
        code, output, error, run = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), {"claim": "Changed request fields"})
        self.assertEqual(json.loads(error)["usage"]["input_tokens"], 12)
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
        self.assertIn('approval_policy="never"', argv)
        self.assertIn("sandbox_workspace_write.network_access=false", argv)
        self.assertIn('web_search="disabled"', argv)
        self.assertNotIn("--model", argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertEqual(run.call_args.kwargs["timeout"], 90)
        self.assertNotIn("TYPESAFE_API_KEY", run.call_args.kwargs["env"])
        self.assertNotIn("SECRET", output + error)

    def test_successful_exit_without_completed_turn_is_rejected(self):
        code, output, error, _ = self.invoke(events=[{"type": "turn.failed", "error": {"message": "SECRET"}}])
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("completed turn", error)
        self.assertNotIn("SECRET", error)

    def test_provider_failure_does_not_echo_private_stderr(self):
        code, output, error, _ = self.invoke(returncode=1)
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("exited with status 1", error)
        self.assertNotIn("SECRET", error)

    def test_missing_final_message_is_rejected(self):
        code, output, error, _ = self.invoke(claim=None)
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("no final message", error)

    def test_invalid_events_are_rejected(self):
        code, output, error, _ = self.invoke(events="not-json")
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("malformed JSON", error)

    def test_timeout_is_failure(self):
        code, output, error, _ = self.invoke(raises=subprocess.TimeoutExpired("codex", 90))
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("TimeoutExpired", error)

    def test_modifying_other_files_is_failure(self):
        code, output, error, _ = self.invoke(mutate=lambda: (self.project / "tests.py").write_text("assert True"))
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("outside the allowed", error)

    def test_modifying_app_is_permitted_but_only_claim_is_returned(self):
        code, output, _, _ = self.invoke(mutate=lambda: (self.project / "app.py").write_text("repaired"))
        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(output)), {"claim"})

    def test_non_fixture_path_is_rejected_before_model_call(self):
        self.project = self.root / "user-repository"
        self.project.mkdir()
        (self.project / "app.py").write_text("code")
        self.request["project"] = str(self.project)
        code, output, error, run = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("restricted to copied fixtures", error)
        run.assert_not_called()

    def test_configure_writes_portable_regeneration_recipe(self):
        (self.root / "policy.json").write_text(json.dumps({"max_checks": 10, "worker_timeout": 10}))
        with patch.object(adapter, "LAB_ROOT", self.root), patch.object(adapter.sys, "stdout", io.StringIO()):
            adapter.configure("/bin/codex")
        config = json.loads((self.root / "worker-config-codex.json").read_text())
        policy = json.loads((self.root / "policy-codex.json").read_text())
        self.assertEqual(config["argv"][-2:], ["--codex-bin", "/bin/codex"])
        self.assertEqual(policy["max_seconds"], 300)
        self.assertGreater(policy["worker_timeout"], adapter.TIMEOUT_SECONDS)
        self.assertEqual(policy["max_checks"], 10)


if __name__ == "__main__":
    unittest.main()
