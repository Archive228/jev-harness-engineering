#!/usr/bin/env python3
"""Offline integration matrix; deliberately NOT a measurement of Jev accuracy."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from processes import run_process

ROOT = Path(__file__).resolve().parent


def independent_acceptance(project, timeout=10):
    """Run post-stop observations in a bounded child; never import generated code here."""
    project = Path(project).resolve()
    environment = {key: value for key, value in os.environ.items()
                   if key in ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR")}
    argv = [sys.executable, "-B", str(ROOT / "oracle_runner.py"), str(project)]
    started = time.monotonic()

    def failure(reason, exit_code=None):
        return {"passed": False, "observations": [], "execution_error": reason,
                "exit_code": exit_code, "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}

    try:
        result = run_process(argv, cwd=str(project), env=environment, timeout=timeout)
    except subprocess.TimeoutExpired:
        return failure("oracle_timeout")
    except OSError as exc:
        return failure("oracle_start_error:" + type(exc).__name__)
    if result.returncode != 0:
        return failure("oracle_process_failed", result.returncode)
    try:
        # An application's own logs may precede the runner's final JSON object.
        payload = json.loads(result.stdout.rstrip().splitlines()[-1])
        if not isinstance(payload, dict):
            raise ValueError("Oracle result must be an object")
        if payload.get("kind") == "oracle_execution_error":
            return failure("oracle_execution_error:" + str(payload.get("error", "unknown")), 0)
        observations = payload.get("observations")
        expected_queries = ["blue", "export", "MILK", "does-not-exist"]
        if (payload.get("kind") != "independent_acceptance_completed"
                or not isinstance(observations, list) or len(observations) != len(expected_queries)
                or any(not isinstance(row, dict) or row.get("query") != query
                       or not isinstance(row.get("pass"), bool)
                       for row, query in zip(observations, expected_queries))):
            raise ValueError("Oracle completion protocol invalid")
    except (ValueError, IndexError):
        return failure("invalid_oracle_result_protocol", 0)
    return {"passed": all(row["pass"] for row in observations), "observations": observations,
            "execution_error": None, "exit_code": 0,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="evaluation-" + time.strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    directory = Path(args.out).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in ("correct", "missing-evidence", "stalled"):
        for selector in ("fixed", "all", "jev"):
            out = directory / (case + "-" + selector)
            process = subprocess.run([sys.executable, str(ROOT / "run.py"), "loop", "--mode", "demo",
                                      "--case", case, "--selector", selector, "--out", str(out)],
                                     capture_output=True, text=True, timeout=150)
            if process.returncode not in (0, 2):
                raise RuntimeError(process.stdout + process.stderr)
            result = json.loads((out / "result.json").read_text())
            report = json.loads((out / "evidence-report.json").read_text())
            oracle = independent_acceptance(out / "project")
            row = {"case": case, "selector": selector, "status": result["status"], "reason": result["reason"],
                   "checks": result["checks_executed"], "iterations": result["worker_iterations"],
                   "judge_invocations": result["judge_invocations"], "remote_jev_requests": result["remote_jev_requests"],
                   "unknown_criteria": sum(r["status"] == "unverified" for r in report["criteria"]),
                   "false_complete": result["status"] == "complete" and not oracle["passed"],
                   "independent_acceptance": oracle, "elapsed_ms": result["elapsed_ms"]}
            rows.append(row)
    output = {"kind": "offline_integration_matrix", "all_judge_answers_and_workers_are_synthetic": True,
              "warning": "Three authored fixtures, one deterministic repair, no real Jev/model trial. No accuracy, speed or cost advantage can be inferred.",
              "baseline_note": "fixed runs D1; all runs D1 and D2; both skip Jev shadow annotations. jev uses synthetic D2 choice and synthetic Noul.",
              "oracle_note": "Additional fixed assertions execute after stop and are never passed back into worker/router. This small oracle is also incomplete.",
              "rows": rows}
    (directory / "evaluation.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(str(directory / "evaluation.json"))


if __name__ == "__main__":
    main()
