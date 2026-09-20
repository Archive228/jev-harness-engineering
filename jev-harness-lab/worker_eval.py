#!/usr/bin/env python3
"""Three preregistered toy repairs with a real Codex worker and bounded routing.

Select fixed/all for deterministic routing or jev for live model decisions.
One run per authored fault does not establish superiority or general reliability.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from evidence import snapshot
from evaluate import independent_acceptance
from processes import run_process

ROOT = Path(__file__).resolve().parent
CASE_NAMES = ("ui-title-only", "backend-title-only", "both-title-only")
SELECTORS = ("fixed", "all", "jev")
SOURCE_FILES = ("worker_eval.py", "run.py", "judge.py", "policy.py", "evidence.py",
                "checks.json", "check_runner.py", "worker.py", "processes.py",
                "evaluate.py", "oracle_runner.py", "adapters/codex_cli.py", "task.md")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fault_variants(source):
    if source.count('"fields": ["title"]') != 1 or source.count("for field in fields") != 1:
        raise ValueError("The fixture changed; review and preregister new variants")
    backend_fault = source.replace("for field in fields", 'for field in ["title"]')
    return dict(zip(CASE_NAMES, (source, backend_fault.replace('"fields": ["title"]',
                                                             '"fields": ["title", "description"]'),
                                 backend_fault)))


def prepare(directory, worker_config, policy, selector="fixed"):
    if selector not in SELECTORS:
        raise ValueError("selector must be fixed, all or jev")
    directory = directory.resolve()
    try:
        directory.relative_to((ROOT / "runs").resolve())
    except ValueError:
        raise ValueError("--out must be a new directory under this lab's runs/") from None
    config = json.loads(worker_config.read_text())
    if str((ROOT / "adapters" / "codex_cli.py").resolve()) not in config.get("argv", []):
        raise ValueError("This experiment requires the Codex CLI worker config")
    # Read and fingerprint every experiment input before any model-assisted run.
    policy_bytes = policy.read_bytes()
    source_sha256 = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                     for name in SOURCE_FILES}
    variants = fault_variants((ROOT / "demo-project" / "app.py").read_text())
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    manifest = {"kind": "preregistered_codex_worker_sanity_experiment", "created_at_unix": time.time(),
                "selector": selector, "mode": "live",
                "remote_jev_requests_expected": 0 if selector != "jev" else None,
                "jev_requests_enabled": selector == "jev",
                "source_sha256": source_sha256,
                "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
                "policy": json.loads(policy_bytes), "cases": []}
    for name, source in variants.items():
        seed = directory / (name + "-seed")
        project = seed / "project"
        project.mkdir(parents=True, mode=0o700)
        (project / "app.py").write_text(source)
        (seed / "initial-app.py.txt").write_text(source)
        write_json(seed / "state.json", {"project": str(project), "project_relative_to_state": "project",
                   "snapshot": snapshot(project), "records": [], "case": "missing-evidence",
                   "worker_claim": "The requested search behavior needs independent verification."})
        manifest["cases"].append({"case": name, "initial_sha256": hashlib.sha256(source.encode()).hexdigest(),
                                   "initial_source_file": str((seed / "initial-app.py.txt").relative_to(directory))})
    # Freeze all inputs before the first model-assisted run. No gold solution or
    # oracle observations are included in the state sent to the worker.
    write_json(directory / "manifest.json", manifest)
    return manifest


def worker_usage(out):
    rows = []
    for path in sorted(out.glob("worker-*.json")):
        try:
            worker = json.loads(path.read_text())
        except (ValueError, OSError):
            rows.append({"iteration_file": path.name, "error": "unreadable_worker_record"})
            continue
        try:
            metadata = json.loads(worker.get("stderr", ""))
        except ValueError:
            metadata = {}
        rows.append({"iteration_file": path.name, "synthetic": worker.get("synthetic"),
                     "provider": metadata.get("provider"), "usage": metadata.get("usage")})
    return rows


def diagnostic_actions(out):
    """Return selected diagnostics, preserving event order without inferring execution."""
    path = out / "events.jsonl"
    if not path.exists():
        return [], "events_not_written"
    actions = []
    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            decision = event["decision"]
            if decision.get("action") == "check" and decision.get("check_id") in ("D1", "D2"):
                actions.append({"event_index": event.get("index"), **decision})
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return actions, "incomplete_or_invalid_events"
    return actions, None


def experiment_note(selector):
    if selector == "jev":
        routing = "Live Jev diagnostic routing and shadow annotations with a real Codex worker."
    elif selector == "all":
        routing = "Deterministic routing through both available diagnostics; Jev calls must remain zero."
    else:
        routing = "Fixed diagnostic routing; Jev calls must remain zero."
    return routing + " Three authored toy faults, one run each; no superiority or general reliability claim."


def evaluate(directory, worker_config, policy, selector="fixed"):
    manifest = prepare(directory, worker_config, policy, selector)
    rows = []
    for case in manifest["cases"]:
        name = case["case"]
        seed, out = directory / (name + "-seed"), directory / name
        argv = [sys.executable, "-B", str(ROOT / "run.py"), "loop", "--mode", "live",
                "--selector", selector, "--state", str(seed / "state.json"), "--out", str(out),
                "--worker-config", str(worker_config), "--policy", str(policy)]
        started = time.monotonic()
        result = {}
        try:
            process = run_process(argv, cwd=str(ROOT), timeout=330)
            if process.returncode not in (0, 2):
                raise ValueError("harness_exit_%d" % process.returncode)
            result = json.loads((out / "result.json").read_text())
            if selector != "jev" and (result.get("remote_jev_requests") != 0 or result.get("judge_invocations") != 0):
                raise ValueError("unexpected_judge_call_in_%s_baseline" % selector)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            result.update(status="error", reason=str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        # The post-stop oracle is never fed back into this or subsequent runs.
        oracle = independent_acceptance(seed / "project")
        final_app = seed / "project" / "app.py"
        actions, actions_error = diagnostic_actions(out)
        row = {"case": name, "selector": selector, "initial_sha256": case["initial_sha256"],
               "final_sha256": hashlib.sha256(final_app.read_bytes()).hexdigest() if final_app.is_file() else None,
               "status": result.get("status"), "reason": result.get("reason"),
               "checks": result.get("checks_executed"), "iterations": result.get("worker_iterations"),
               "judge_invocations": result.get("judge_invocations"),
               "remote_jev_requests": result.get("remote_jev_requests"),
               "jev_usage": result.get("usage"), "jev_usage_complete": result.get("usage_complete"),
               "judge_elapsed_ms": result.get("judge_elapsed_ms"),
               "diagnostic_actions": actions, "diagnostic_actions_error": actions_error,
               "worker_calls": worker_usage(out),
               "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
               "harness_elapsed_ms": result.get("elapsed_ms"), "independent_acceptance": oracle,
               "false_complete": result.get("status") == "complete" and not oracle["passed"]}
        rows.append(row)
        write_json(directory / "evaluation.json", {"kind": manifest["kind"], "completed_cases": len(rows),
                   "planned_cases": len(CASE_NAMES), "worker": "real_codex_cli", "selector": selector,
                   "note": experiment_note(selector),
                   "oracle_note": "Four fixed observations after stop; independent from the two acceptance checks, not exhaustive.",
                   "rows": rows})
        lines = ["# Real Codex worker: three toy repairs", "", "Selector: `%s`." % selector, "",
                 experiment_note(selector), ""]
        for row in rows:
            lines += ["## " + row["case"], "", "- Harness: **%s** (%s)." % (row["status"], row["reason"]),
                      "- Worker corrections: %s. Executed checks: %s." % (row["iterations"], row["checks"]),
                      "- Selected diagnostics: %s; event-log status: %s." %
                      (", ".join(action["check_id"] for action in row["diagnostic_actions"]) or "none recorded",
                       row["diagnostic_actions_error"] or "readable"),
                      "- Judge invocations: %s. Remote Jev requests: %s." %
                      (row["judge_invocations"], row["remote_jev_requests"]),
                      "- Jev usage: `%s`; completeness: `%s`; judge latency: %s ms." %
                      (json.dumps(row["jev_usage"], sort_keys=True), row["jev_usage_complete"], row["judge_elapsed_ms"]),
                      "- Post-stop independent acceptance: **%s**. False complete: **%s**." %
                      (row["independent_acceptance"]["passed"], row["false_complete"]),
                      "- Wall time including final oracle: %.2f seconds." % (row["elapsed_ms"] / 1000), ""]
        (directory / "evaluation.md").write_text("\n".join(lines))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "runs" / ("worker-eval-" + time.strftime("%Y%m%d-%H%M%S"))))
    parser.add_argument("--worker-config", default=str(ROOT / "worker-config-codex.json"))
    parser.add_argument("--policy", default=str(ROOT / "policy-codex.json"))
    parser.add_argument("--selector", choices=SELECTORS, default="fixed")
    args = parser.parse_args()
    directory = Path(args.out).resolve()
    rows = evaluate(directory, Path(args.worker_config).resolve(), Path(args.policy).resolve(), args.selector)
    print(str(directory / "evaluation.md"))
    return 0 if all(row["status"] == "complete" and row["independent_acceptance"]["passed"] for row in rows) else 2


if __name__ == "__main__":
    sys.exit(main())
