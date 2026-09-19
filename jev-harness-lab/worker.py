"""External worker protocol and a deterministic demo repair."""
import json
import os
from pathlib import Path
import subprocess
from processes import run_process


class WorkerError(RuntimeError):
    pass


def run_worker(mode, state, task, feedback, iteration, config_path, timeout):
    if mode == "demo":
        if state["case"] == "stalled":
            return {"claim": "SYNTHETIC DEMO: says done but makes no change.", "synthetic": True}
        path = Path(state["project"]) / "app.py"
        source = path.read_text()
        old = '"fields": ["title"]'
        if old not in source:
            raise WorkerError("Demo fixture unexpectedly changed")
        path.write_text(source.replace(old, '"fields": ["title", "description"]'))
        return {"claim": "SYNTHETIC DEMO: expanded request fields to title and description.", "synthetic": True}
    if not config_path:
        raise WorkerError("Live loop requires --worker-config path.json")
    config = json.loads(Path(config_path).read_text())
    if not isinstance(config, dict):
        raise WorkerError("Worker config must be a JSON object")
    argv = config.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
        raise WorkerError("Worker config requires a nonempty argv array of strings")
    request = {"task": task, "project": state["project"], "feedback": feedback, "iteration": iteration}
    environment = dict(os.environ)
    environment.pop("TYPESAFE_API_KEY", None)
    try:
        result = run_process(argv, input=json.dumps(request),
                             cwd=state["project"], env=environment, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise WorkerError("worker_timeout") from None
    except OSError as exc:
        raise WorkerError("Worker could not start: " + type(exc).__name__) from None
    if result.returncode != 0:
        raise WorkerError("Worker exited with code %d" % result.returncode)
    try:
        output = json.loads(result.stdout)
    except ValueError:
        raise WorkerError("Worker stdout must be exactly one JSON object") from None
    if not isinstance(output, dict) or not isinstance(output.get("claim"), str):
        raise WorkerError("Worker result requires string claim")
    return {"claim": output["claim"][:8000], "synthetic": False,
            "adapter": argv[0], "stderr": result.stderr[:16000]}
