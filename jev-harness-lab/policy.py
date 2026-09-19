"""The policy owns actions and limits. It never accepts arbitrary model commands."""
import json
import math
from pathlib import Path
from evidence import CHECKS

DEFAULT_PATH = Path(__file__).resolve().parent / "policy.json"


def load_policy(path=DEFAULT_PATH):
    value = json.loads(Path(path).read_text())
    required = json.loads(DEFAULT_PATH.read_text())
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError("Policy fields must be exactly: " + ", ".join(required))
    for key, item in value.items():
        if not isinstance(item, (int, float)) or isinstance(item, bool) or not math.isfinite(item):
            raise ValueError("Policy values must be finite numbers")
        if key in ("scope_threshold", "min_choice_confidence"):
            if not 0 <= item <= 1:
                raise ValueError("Threshold outside [0,1]")
        elif item <= 0:
            raise ValueError("Limits must be positive")
        elif key in ("max_iterations", "max_checks", "max_jev_calls") and not isinstance(item, int):
            raise ValueError("Counts must be integers")
    return value


def decide(context, policy):
    if context["elapsed_seconds"] >= policy["max_seconds"]:
        return {"action": "stop", "reason": "time_limit"}
    rows = context["report"]["criteria"]
    expected = {(key, check["criterion"]) for key, check in CHECKS.items()
                if check["kind"] == "mandatory"}
    if (not isinstance(rows, list) or len(rows) != len(expected)
            or any(not isinstance(row, dict) for row in rows)
            or any(not isinstance(row.get(key), str) for row in rows
                   for key in ("check_id", "criterion", "status"))
            or {(row.get("check_id"), row.get("criterion")) for row in rows} != expected
            or any(row.get("status") not in ("passed", "failed", "unverified") for row in rows)):
        return {"action": "stop", "reason": "invalid_acceptance_report"}
    # Known check-to-requirement mappings are deterministic; Noul stays shadow-only.
    statuses = [row["status"] for row in rows]
    if statuses and all(status == "passed" for status in statuses):
        return {"action": "complete", "reason": "acceptance_contract_satisfied"}
    for row in rows:
        if row["reason"] == "no_fresh_execution":
            if context["checks_used"] >= policy["max_checks"]:
                return {"action": "stop", "reason": "check_limit"}
            return {"action": "check", "check_id": row["check_id"], "reason": "mandatory_acceptance"}
    if "unverified" in statuses:
        return {"action": "stop", "reason": "evidence_requires_review"}
    if context.get("diagnostic_errors"):
        return {"action": "stop", "reason": "diagnostic_tool_error"}
    selector = context.get("selector", "jev")
    pending = context.get("diagnostics_pending", ["D1", "D2"])
    if selector in ("fixed", "all") and pending and (selector == "all" or not context["diagnostics_done"]):
        if context["checks_used"] >= policy["max_checks"]:
            return {"action": "stop", "reason": "check_limit"}
        return {"action": "check", "check_id": pending[0], "reason": selector + "_diagnostic"}
    if context["diagnostics_done"]:
        if context["iterations"] >= policy["max_iterations"]:
            return {"action": "stop", "reason": "iteration_limit"}
        return {"action": "worker", "reason": "repair_observed_failure"}
    if not context["router_asked"]:
        if context["jev_calls"] >= policy["max_jev_calls"]:
            return {"action": "stop", "reason": "jev_call_limit"}
        return {"action": "ask_router", "reason": "choose_optional_diagnostic"}
    choice = context.get("router_answer") or {}
    selected = choice.get("choice")
    if selected not in ("D1", "D2") or choice.get("confidence", 0) < policy["min_choice_confidence"]:
        return {"action": "stop", "reason": "no_supported_diagnostic"}
    if context["checks_used"] >= policy["max_checks"]:
        return {"action": "stop", "reason": "check_limit"}
    return {"action": "check", "check_id": selected, "reason": "jev_selected_diagnostic"}
