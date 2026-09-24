"""Re-decide saved turns from their journal, without a model and without a workspace.

A decision event carries the facts the policy read and the verdict it produced.
Replay recomputes the verdict twice: under the thresholds recorded with the
event (a regression check on the decision code) and under the thresholds in
force today (what a policy change would do to real history). Neither path calls
Jev, Codex or the filesystem beyond reading events.jsonl, so replay costs
nothing and works on a session whose workspace is long gone.
"""
import json
from pathlib import Path

from .decision import POLICY_VERSION, decide_turn, thresholds


def read_decisions(directory):
    """Decision events of a saved session, oldest first."""
    path = Path(directory) / "events.jsonl"
    if not path.is_file():
        raise ValueError("session has no event journal: " + str(path))
    decisions = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue  # A half-written final record must not hide the rest.
        if not isinstance(event, dict) or event.get("type") != "decision":
            continue
        data = event.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("inputs"), dict) \
                or not isinstance(data.get("verdict"), dict):
            continue
        decisions.append({"seq": event.get("seq"), "turn": event.get("turn"), **data})
    return decisions


def _compare(recorded, recomputed):
    return {key: {"recorded": recorded.get(key), "recomputed": recomputed.get(key)}
            for key in ("outcome", "status", "reason", "threshold", "checks_blocked")
            if recorded.get(key) != recomputed.get(key)}


def replay_session(directory):
    """Recompute every recorded decision. Returns a report; performs no writes."""
    current = thresholds()
    turns, mismatches, drifted = [], 0, 0
    for decision in read_decisions(directory):
        recorded_policy = decision.get("thresholds")
        try:
            as_recorded = decide_turn(policy=thresholds(recorded_policy) if recorded_policy else None,
                                      **decision["inputs"])
            as_current = decide_turn(policy=current, **decision["inputs"])
        except (ValueError, KeyError, TypeError) as exc:
            turns.append({"turn": decision.get("turn"), "seq": decision.get("seq"),
                          "error": str(exc)})
            mismatches += 1
            continue
        difference = _compare(decision["verdict"], as_recorded)
        drift = _compare(as_recorded, as_current)
        mismatches += bool(difference)
        drifted += bool(drift)
        turns.append({"turn": decision.get("turn"), "seq": decision.get("seq"),
                      "attempt": decision["inputs"].get("attempt"),
                      "recorded_policy_version": decision.get("policy_version"),
                      "verdict": decision["verdict"], "reproduced": not difference,
                      "difference": difference or None, "policy_drift": drift or None})
    return {"session": str(Path(directory).resolve()), "decisions": len(turns),
            "reproduced": len(turns) - mismatches, "mismatches": mismatches,
            "changed_by_current_policy": drifted,
            "current_policy_version": POLICY_VERSION, "current_thresholds": current,
            "turns": turns}
