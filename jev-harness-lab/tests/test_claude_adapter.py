import importlib.util
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "adapters" / "claude_code.py"
SPEC = importlib.util.spec_from_file_location("claude_adapter", PATH)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


class AdapterContractTests(unittest.TestCase):
    def invoke(self, provider_result):
        request = {"project": str(Path.cwd()), "task": "Repair search", "feedback": {}, "iteration": 1}
        with patch.object(adapter.sys, "argv", [str(PATH)]), \
                patch.object(adapter.sys, "stdin", io.StringIO(json.dumps(request))), \
                patch.object(adapter.sys, "stdout", io.StringIO()) as output, \
                patch.object(adapter.sys, "stderr", io.StringIO()) as error, \
                patch.dict(adapter.os.environ, {"ANTHROPIC_API_KEY": "TEST-NOT-A-KEY"}), \
                patch.object(adapter.subprocess, "run", return_value=provider_result) as run:
            code = adapter.main()
            return code, output.getvalue(), error.getvalue(), run

    def test_worker_json_and_bounded_file_tools(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"result": "Changed app.py", "is_error": False, "total_cost_usd": .01}), "")
        code, output, error, run = self.invoke(result)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), {"claim": "Changed app.py"})
        argv = run.call_args.args[0]
        self.assertIn("--restricted", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Edit")
        self.assertEqual(run.call_args.kwargs["timeout"], 80)
        self.assertNotIn("TEST-NOT-A-KEY", output + error)

    def test_zero_exit_provider_error_is_not_worker_success(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"is_error": True, "result": "failed"}), "")
        code, output, error, _ = self.invoke(result)
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertIn("error result", error)

    def test_malformed_provider_output_stops_cleanly(self):
        result = subprocess.CompletedProcess([], 0, "not json", "")
        code, output, _, _ = self.invoke(result)
        self.assertEqual(code, 1)
        self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
