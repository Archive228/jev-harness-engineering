#!/usr/bin/env python3
"""Independent CLI acceptance. This file stays outside the editable workspace."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


CHECK_IDS = ("timestamps", "duplicates", "malformed", "severity", "artifacts", "combined")


class CheckFailure(AssertionError):
    pass


def require(condition, detail):
    if not condition:
        raise CheckFailure(detail)


def equal(actual, expected, label):
    require(actual == expected, "%s: expected %r, got %r" % (label, expected, actual))


def event(identity, timestamp="2026-09-20T09:00:00Z", service="api", severity="INFO", message="Probe"):
    return {"event_id": identity, "timestamp": timestamp, "service": service,
            "severity": severity, "message": message}


def encode(items):
    return "\n".join(item if isinstance(item, str) else json.dumps(item) for item in items) + "\n"


def run_cli(project, items):
    script = project / "loglab.py"
    require(script.is_file(), "Missing CLI loglab.py")
    with tempfile.TemporaryDirectory(prefix="loglab-oracle-") as temporary:
        directory = Path(temporary)
        source = directory / "input.jsonl"
        output = directory / "nested" / "report.json"
        markdown = directory / "nested" / "report.md"
        source.write_text(encode(items), encoding="utf-8")
        argv = [sys.executable, "-B", str(script), str(source), "--json", str(output), "--markdown", str(markdown)]
        environment = {key: value for key, value in os.environ.items()
                       if key in ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR")}
        try:
            result = subprocess.run(argv, cwd=str(project), env=environment, text=True,
                                    capture_output=True, timeout=8)
        except subprocess.TimeoutExpired:
            raise CheckFailure("CLI exceeded 8-second acceptance deadline") from None
        require(result.returncode == 0, "CLI exited %d: %s" % (result.returncode, result.stderr[-1800:].strip()))
        require(output.is_file() and markdown.is_file(), "CLI did not write both requested report artifacts")
        require(output.stat().st_size <= 2_000_000 and markdown.stat().st_size <= 2_000_000,
                "Unexpectedly large report")
        try:
            report = json.loads(output.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise CheckFailure("CLI report is not valid UTF-8 JSON") from None
        require(isinstance(report, dict), "JSON report must be an object")
        return report, markdown.read_text(encoding="utf-8")


def check_timestamps(project):
    items = [event("late", "2026-09-20T06:30:00-04:00"),
             event("early", "2026-09-20T12:00:00+03:00"),
             event("middle-b", "2026-09-20T09:30:00Z"),
             event("middle-a", "2026-09-20T10:30:00+01:00")]
    report, _ = run_cli(project, items)
    equal([row["event_id"] for row in report["timeline"]], ["early", "middle-a", "middle-b", "late"], "UTC order and event_id tiebreak")
    equal(report["first_timestamp"], "2026-09-20T09:00:00.000000Z", "first_timestamp")
    equal(report["last_timestamp"], "2026-09-20T10:30:00.000000Z", "last_timestamp")
    equal([row["timestamp"] for row in report["timeline"]], ["2026-09-20T09:00:00.000000Z", "2026-09-20T09:30:00.000000Z", "2026-09-20T09:30:00.000000Z", "2026-09-20T10:30:00.000000Z"], "normalized timeline")


def check_duplicates(project):
    items = [event("same", service="database", severity="ERROR", message="Original"),
             event("other", service="edge"),
             event("same", service="edge", severity="INFO", message="Conflicting retransmission"),
             event("same", service="api", severity="FATAL", message="Third retransmission")]
    report, _ = run_cli(project, items)
    equal(report["total_events"], 2, "unique event count")
    equal(report["duplicate_events"], 2, "duplicate count")
    equal(report["by_severity"], {"ERROR": 1, "INFO": 1}, "deduplicated severity counts")
    equal(report["by_service"], {"database": 1, "edge": 1}, "first valid event wins")
    same = [row for row in report["timeline"] if row["event_id"] == "same"]
    equal(len(same), 1, "unique timeline IDs")
    equal(same[0]["message"], "Original", "original event retained")


def check_malformed(project):
    missing = event("missing")
    del missing["message"]
    invalid = ["{broken", [], missing, event("naive", "2026-09-20T09:00:00"),
               event("bad-date", "not-a-date"), event("bad-severity", severity="PANIC"),
               event("empty-message", message="  ")]
    report, _ = run_cli(project, [event("before"), "", "   "] + invalid + [event("after")])
    equal(report["malformed_lines"], 7, "malformed line count; blanks excluded")
    equal(report["total_events"], 2, "valid lines after malformed input survive")
    equal(report["duplicate_events"], 0, "malformed records are not duplicates")
    equal([row["event_id"] for row in report["timeline"]], ["after", "before"], "valid event IDs")
    empty, _ = run_cli(project, ["", " "])
    equal(empty["total_events"], 0, "empty stream count")
    equal(empty["first_timestamp"], None, "empty stream first timestamp")
    equal(empty["last_timestamp"], None, "empty stream last timestamp")
    equal(empty["incident"], {"candidate_service": None, "evidence_ids": []}, "empty incident")


def check_severity(project):
    items = [event("w", service="api", severity="warning"),
             event("e2", service="beta", severity="err"),
             event("e1", service="alpha", severity="error"),
             event("f1", service="alpha", severity="fatal"),
             event("f2", service="beta", severity="FATAL"),
             event("i", service="edge", severity="iNfO")]
    report, markdown = run_cli(project, items)
    equal(report["by_severity"], {"WARN": 1, "ERROR": 2, "FATAL": 2, "INFO": 1}, "severity normalization")
    equal(report["incident"], {"candidate_service": "alpha", "evidence_ids": ["e1", "f1"]}, "candidate tie and direct evidence")
    require("Hypothesis" in markdown and "alpha" in markdown and "e1" in markdown and "f1" in markdown,
            "Markdown must identify a hypothesis and its concrete evidence")


def check_artifacts(project):
    report, markdown = run_cli(project, [event("proof-id", severity="ERROR", message="upstream | timeout")])
    equal(report["total_events"], 1, "artifact event count")
    for fragment in ("# Incident report", "## Timeline", "proof-id", "api", "Hypothesis", "upstream \\| timeout"):
        require(fragment in markdown, "Markdown missing %r" % fragment)
    for key in ("total_events", "duplicate_events", "malformed_lines"):
        require(isinstance(report[key], int) and not isinstance(report[key], bool), key + " must be an integer")
    for label, value in (("Total events", 1), ("Duplicate events", 0), ("Malformed lines", 0)):
        require("%s: %d" % (label, value) in markdown, "Markdown missing accurate " + label)


def check_combined(project):
    missing = event("missing")
    del missing["message"]
    items = [event("end", "2026-09-20T09:03:00Z", "edge", "INFO"),
             event("e3", "2026-09-20T04:01:00-05:00", "database", "fatal"),
             "{truncated", event("e2", "2026-09-20T10:00:00+01:00", "api", "err"),
             event("e3", "2026-09-20T09:10:00Z", "edge", "INFO"),
             event("start", "2026-09-20T08:59:00Z", "edge", "info"),
             missing, [], event("naive", "2026-09-20T09:00:00"),
             event("unknown", severity="BOGUS"),
             event("e4", "2026-09-20T09:01:00Z", "database", "ERROR"),
             event("e5", "2026-09-20T09:02:00Z", "api", "WARNING")]
    report, markdown = run_cli(project, items)
    equal(report["total_events"], 6, "combined total")
    equal(report["duplicate_events"], 1, "combined duplicates")
    equal(report["malformed_lines"], 5, "combined malformed")
    equal(report["by_service"], {"edge": 2, "api": 2, "database": 2}, "combined service counts")
    equal(report["by_severity"], {"INFO": 2, "ERROR": 2, "FATAL": 1, "WARN": 1}, "combined severity counts")
    equal([row["event_id"] for row in report["timeline"]], ["start", "e2", "e3", "e4", "e5", "end"], "combined timeline")
    equal(report["first_timestamp"], "2026-09-20T08:59:00.000000Z", "combined first timestamp")
    equal(report["last_timestamp"], "2026-09-20T09:03:00.000000Z", "combined last timestamp")
    equal(report["incident"], {"candidate_service": "database", "evidence_ids": ["e3", "e4"]}, "combined hypothesis evidence")
    require("e3" in markdown and "e4" in markdown and "Hypothesis" in markdown, "Combined report lost hypothesis evidence")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", required=True)
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.check not in CHECK_IDS:
            raise ValueError("Unknown registered check: " + args.check)
        project = args.project.resolve(strict=True)
        globals()["check_" + args.check](project)
    except CheckFailure as exc:
        print(json.dumps({"passed": False, "check_id": args.check, "detail": str(exc)}))
        return 1
    except (KeyError, TypeError, ValueError, OSError) as exc:
        print(json.dumps({"passed": False, "check_id": args.check, "detail": type(exc).__name__ + ": " + str(exc)}))
        return 2
    print(json.dumps({"passed": True, "check_id": args.check, "detail": "Independent CLI acceptance passed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
