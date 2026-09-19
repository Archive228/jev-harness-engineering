"""Private post-stop assertions; called only by the bounded evaluator subprocess."""
import importlib.util
import json
from pathlib import Path
import sys


def run(project):
    spec = importlib.util.spec_from_file_location("oracle_app", str(Path(project) / "app.py"))
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    observations = []
    for query, expected in [("blue", [1]), ("export", [2]), ("MILK", [1]), ("does-not-exist", [])]:
        try:
            actual = [item["id"] for item in app.search(query)]
            observations.append({"query": query, "expected": expected, "actual": actual, "pass": actual == expected})
        except (Exception, SystemExit) as exc:
            observations.append({"query": query, "pass": False, "error": type(exc).__name__})
    return {"kind": "independent_acceptance_completed", "observations": observations}


if __name__ == "__main__":
    try:
        print(json.dumps(run(sys.argv[1]), ensure_ascii=False))
    except (Exception, SystemExit) as exc:
        print(json.dumps({"kind": "oracle_execution_error", "error": type(exc).__name__}))
