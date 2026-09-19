#!/usr/bin/env python3
"""Small preregistered live Jev evaluation. Never substitutes synthetic responses."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

from judge import ENDPOINT, MODEL, Judge, JudgeError, validate_response

ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "fixtures" / "live-eval-cases.json"
PROTOCOL_VERSION = "jev-live-eval-v1"
MAX_REQUESTS = 18
CHOICE_CONFIDENCE = 0.60
NOUL_LOW = 0.20
NOUL_HIGH = 0.80

SUPPORT_QUESTIONS = {
    "category": {
        "type": "choice",
        "instructions": "Classify the actual problem the customer asks to fix. Ignore features explicitly described as working normally.",
        "criteria": {
            "export": "Exporting, generating or downloading a document or file",
            "account": "Signing in, authentication or access to an account",
            "payment": "Billing, invoices, subscription payments or billing details",
            "other": "A different problem outside the three categories above",
        },
    },
    "has_workaround": {
        "type": "noul",
        "instructions": "Does this customer's message explicitly report an alternative method that they have actually used successfully to accomplish the affected task? Advice, an untried suggestion, a question, and a failed alternative do not count.",
    },
}
DIAGNOSTIC_QUESTIONS = {
    "next_check": {
        "type": "choice",
        "instructions": "Select the next diagnostic that adds missing evidence about the observed failure on the CURRENT source snapshot. Do not repeat a diagnostic already completed with fresh evidence. Stale results do not count as fresh evidence. Select none_suitable when both diagnostics are already covered, neither can run, or neither addresses the failure.",
        "criteria": {
            "D1": "Bypass the UI request builder and call the backend with both title and description fields. This reveals backend filtering behavior. It requires importing app.py.",
            "D2": "Inspect the outgoing search request built by the UI to reveal whether its fields parameter includes description. It requires importing app.py.",
            "none_suitable": "Neither available diagnostic adds relevant, executable, fresh evidence for this failure.",
        },
    },
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def load_cases(path=CASES_PATH):
    document = json.loads(Path(path).read_text())
    cases = document["cases"]
    if not 1 <= len(cases) <= MAX_REQUESTS:
        raise ValueError("Evaluation must contain 1..18 cases")
    ids = set()
    for case in cases:
        if set(case) != {"id", "kind", "language", "state", "expected"}:
            raise ValueError("Unexpected case fields")
        if case["id"] in ids or case["language"] not in ("en", "ru"):
            raise ValueError("Invalid or duplicate case identity")
        ids.add(case["id"])
        if case["kind"] not in ("support", "diagnostic") or not isinstance(case["state"], dict):
            raise ValueError("Invalid case kind/state")
        questions = questions_for(case)
        if set(case["expected"]) != set(questions):
            raise ValueError("Expected labels must exactly match questions")
        for key, question in questions.items():
            gold = case["expected"][key]
            if question["type"] == "noul" and not isinstance(gold, bool):
                raise ValueError("Noul gold must be boolean")
            if question["type"] == "choice" and gold not in question["criteria"]:
                raise ValueError("Choice gold outside criteria")
        # Metadata and labels must remain outside the payload state.
        if any(key in case["state"] for key in ("expected", "gold", "answer", "label")):
            raise ValueError("Gold-like state field rejected")
    return document


def questions_for(case):
    return SUPPORT_QUESTIONS if case["kind"] == "support" else DIAGNOSTIC_QUESTIONS


def make_request(case, model):
    return {"state": case["state"], "model": model, "questions": questions_for(case)}


def baseline_label(case, question_id):
    """Predeclared weak controls, not tuned or advertised as competitive."""
    if case["kind"] == "diagnostic":
        return "D1"  # Fixed diagnostic order, regardless of supplied observations.
    if question_id == "has_workaround":
        return False  # Constant negative control; no semantic reasoning claimed.
    ticket = case["state"]["ticket"].lower()
    # Deliberately simple topic matching cannot resolve negation or focus reliably.
    terms = (("payment", ("invoice", "billing", "payment", "pay", "счёт", "оплат", "платёж", "подписк")),
             ("account", ("sign-in", "signing in", "log in", "password", "войти", "вход")),
             ("export", ("download", "export", "csv", "pdf", "скачать", "экспорт")))
    for label, words in terms:
        if any(word in ticket for word in words):
            return label
    return "other"


def score_answer(case, key, answer):
    gold = case["expected"][key]
    if answer["type"] == "noul":
        raw_label = answer["noul"] >= 0.5
        abstained = NOUL_LOW < answer["noul"] < NOUL_HIGH
    else:
        raw_label = answer["choice"]
        abstained = answer["confidence"] < CHOICE_CONFIDENCE
    baseline = baseline_label(case, key)
    return {
        "case_id": case["id"], "kind": case["kind"], "language": case["language"],
        "question": key, "expected": gold, "raw_label": raw_label,
        "raw_correct": raw_label == gold,
        "policy_label": None if abstained else raw_label,
        "policy_abstained": abstained,
        "policy_correct": None if abstained else raw_label == gold,
        "explicit_none_suitable": not abstained and raw_label == "none_suitable",
        "baseline_label": baseline, "baseline_correct": baseline == gold,
    }


def ratio(a, b):
    return round(a / b, 6) if b else None


def summarize(rows, expected_count):
    correct = sum(row["raw_correct"] for row in rows)
    accepted = [row for row in rows if not row["policy_abstained"]]
    accepted_correct = sum(row["policy_correct"] for row in accepted)
    return {
        "expected_answers": expected_count,
        "valid_answers": len(rows), "unanswered": expected_count - len(rows),
        "raw_correct": correct, "raw_accuracy_on_valid": ratio(correct, len(rows)),
        "policy_abstentions": sum(row["policy_abstained"] for row in rows),
        "accepted_decisions": len(accepted), "accepted_correct": accepted_correct,
        "accepted_incorrect": len(accepted) - accepted_correct,
        "decision_coverage": ratio(len(accepted), expected_count),
        "accuracy_on_accepted": ratio(accepted_correct, len(accepted)),
        "explicit_none_suitable": sum(row["explicit_none_suitable"] for row in rows),
    }


def baseline_summary(cases):
    grouped = {}
    for case in cases:
        for key, gold in case["expected"].items():
            grouped.setdefault(key, []).append(baseline_label(case, key) == gold)
    return {key: {"correct": sum(values), "total": len(values), "accuracy": ratio(sum(values), len(values))}
            for key, values in grouped.items()}


def render_report(result):
    lines = ["# Small live Jev evaluation", "",
             "Mode: **%s**. Status: **%s**." % (result["mode"], result["status"]), "",
             "This is an authored, preregistered 18-case check of the API and narrow decisions; it is not a representative benchmark or an estimate of production reliability.", "",
             "Requested model: `%s`. Dataset SHA-256: `%s`." % (result["requested_model"], result["dataset_sha256"]), "",
             "Actual remote requests: %s. Valid responses: %s. Errors: %s." % (result["remote_requests"], result["valid_responses"], result["request_errors"]), ""]
    if result["mode"] != "live":
        lines.extend(["No Jev predictions were generated. Prepared requests and local baseline scores are not live model results.", ""])
    else:
        m = result["metrics"]
        lines.extend(["Raw labels correct: **%s / %s valid answers** (%s expected answers, %s unanswered)." % (m["raw_correct"], m["valid_answers"], m["expected_answers"], m["unanswered"]), "",
                      "Policy: %s accepted decisions, %s correct, %s incorrect; %s confidence/uncertainty abstentions. Coverage: %s. Explicit `none_suitable`: %s." % (m["accepted_decisions"], m["accepted_correct"], m["accepted_incorrect"], m["policy_abstentions"], m["decision_coverage"], m["explicit_none_suitable"]), ""])
        for key, group in result["by_question"].items():
            lines.append("- `%s`: raw %s/%s; accepted %s/%s; uncertainty abstentions %s; unanswered %s." % (key, group["raw_correct"], group["valid_answers"], group["accepted_correct"], group["accepted_decisions"], group["policy_abstentions"], group["unanswered"]))
        lines.extend(["", "Reported API tokens: %s input, %s output. Sum of request durations: %s ms. These durations include network overhead and are not model-only latency." % (result["usage"]["input_tokens"], result["usage"]["output_tokens"], result["total_request_ms"]), ""])
    lines.extend(["## Fixed local controls", "", "Category: fixed keyword rules; workaround: always false; diagnostic: always D1. These weak controls are transparent reference points, not tuned competitive baselines.", ""])
    for key, metric in result["baseline"].items():
        lines.append("- `%s`: %s/%s." % (key, metric["correct"], metric["total"]))
    lines.extend(["", "## Interpretation", "", "Questions and labels were frozen before this run. No threshold is fitted to these cases: Choice confidence ≥0.60 is accepted; Noul ≤0.20 means no, ≥0.80 means yes, and the middle band abstains. Raw Noul labels use 0.5 only for reporting raw accuracy. `none_suitable` is an explicit potentially correct decision, counted separately from uncertainty abstention.", "", "No worker is run here. These results do not establish end-to-end repair quality, monetary savings, or superiority over a well-designed deterministic router. Each request and unmodified provider response is recorded separately; no provider explanation is invented.", ""])
    return "\n".join(lines)


def evaluate(out, dry_run=False, model=MODEL, timeout=20, cases_path=CASES_PATH, judge_factory=Judge):
    if not math.isfinite(timeout) or not 0 < timeout <= 30:
        raise ValueError("timeout must be greater than 0 and at most 30 seconds")
    document = load_cases(cases_path)
    cases = document["cases"]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "requests").mkdir()
    expected_count = sum(len(case["expected"]) for case in cases)
    mode = "dry-run" if dry_run else ("live" if os.environ.get("TYPESAFE_API_KEY") else "no-credentials")
    result = {
        "protocol": PROTOCOL_VERSION, "mode": mode, "status": "prepared",
        "started_at": datetime.now(timezone.utc).isoformat(), "requested_model": model,
        "endpoint": ENDPOINT, "dataset_version": document["version"],
        "dataset_sha256": digest(document),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "client_sha256": hashlib.sha256((ROOT / "judge.py").read_bytes()).hexdigest(),
        "python_version": sys.version.split()[0],
        "questions_sha256": digest({"support": SUPPORT_QUESTIONS, "diagnostic": DIAGNOSTIC_QUESTIONS}),
        "thresholds": {"choice_confidence_min": CHOICE_CONFIDENCE, "noul_no_max": NOUL_LOW, "noul_yes_min": NOUL_HIGH},
        "timeout_seconds": timeout, "max_requests": MAX_REQUESTS, "automatic_retries": 0,
        "remote_requests": 0, "valid_responses": 0, "request_errors": 0,
        "usage": {"input_tokens": 0, "output_tokens": 0}, "total_request_ms": 0,
        "baseline": baseline_summary(cases), "requests": [], "answers": [],
    }
    write_json(out / "dataset.json", document)
    for case in cases:
        request = make_request(case, model)
        write_json(out / "requests" / (case["id"] + ".json"), request)
    write_json(out / "protocol.json", {key: value for key, value in result.items() if key not in ("baseline", "requests", "answers")})
    judge = judge_factory("live", out / "judge", timeout=timeout, model=model) if mode == "live" else None
    abort_reason = None
    for case in cases:
        item = {"case_id": case["id"], "request_sha256": digest(make_request(case, model)), "status": "prepared"}
        if judge is None:
            item["status"] = "not_sent"
        elif abort_reason:
            item.update(status="skipped_after_error", reason=abort_reason)
        else:
            started = time.monotonic()
            try:
                response = judge.ask(case["state"], questions_for(case))
                validate_response(response, questions_for(case))
                # Keep the entire provider JSON, not a reconstructed result.
                write_json(out / (case["id"] + "-response.json"), response)
                item.update(status="ok", response_model=response.get("model"),
                            provider_metadata={key: response[key] for key in ("id", "system_fingerprint", "fingerprint", "version", "model_version") if key in response},
                            usage=response.get("usage"), response_path=case["id"] + "-response.json")
                result["valid_responses"] += 1
                result["answers"].extend(score_answer(case, key, response["answers"][key]) for key in questions_for(case))
            except JudgeError as exc:
                result["request_errors"] += 1
                abort_reason = str(exc)
                item.update(status="error", error=abort_reason)
            item["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
        result["requests"].append(item)
        if judge is not None:
            result["remote_requests"] = judge.remote_requests
            result["usage"] = dict(judge.usage)
            result["total_request_ms"] = round(judge.total_ms, 2)
        # Save progress even if the process is interrupted between requests.
        write_json(out / "progress.json", result)
    if judge is not None:
        result["remote_requests"] = judge.remote_requests
        result["usage"] = judge.usage
        result["total_request_ms"] = round(judge.total_ms, 2)
    result["metrics"] = summarize(result["answers"], expected_count)
    counts = Counter(key for case in cases for key in case["expected"])
    result["by_question"] = {key: summarize([row for row in result["answers"] if row["question"] == key], count) for key, count in counts.items()}
    result["status"] = "error" if abort_reason else ("completed" if mode == "live" else ("credentials_required" if mode == "no-credentials" else "prepared"))
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(out / "results.json", result)
    (out / "report.md").write_text(render_report(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="New output directory; existing directories are never overwritten")
    parser.add_argument("--dry-run", action="store_true", help="Save protocol/requests; make no network calls and generate no Jev answers")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()
    try:
        result = evaluate(args.out, args.dry_run, args.model, args.timeout)
    except (ValueError, OSError, KeyError) as exc:
        print("Evaluation setup failed: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"out": str(Path(args.out).resolve()), "mode": result["mode"], "status": result["status"], "remote_requests": result["remote_requests"], "metrics": result["metrics"]}, indent=2))
    return 0 if result["status"] in ("completed", "prepared") else 1


if __name__ == "__main__":
    sys.exit(main())
