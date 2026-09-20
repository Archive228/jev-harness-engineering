"""Aggregate events into an incident report."""
from collections import Counter

from .parser import parse_events


def analyze(text):
    events, malformed = parse_events(text)
    unique = list(events)
    duplicates = 0
    ordered = sorted(unique, key=lambda event: (event["_sort_key"], event["event_id"]))
    timeline = [{key: value for key, value in event.items() if not key.startswith("_")}
                for event in ordered]
    errors = Counter(event["service"] for event in timeline if event["severity"] in ("ERROR", "FATAL"))
    candidate = sorted(errors, key=lambda service: (-errors[service], service))[0] if errors else None
    return {
        "total_events": len(timeline),
        "duplicate_events": duplicates,
        "malformed_lines": malformed,
        "first_timestamp": timeline[0]["timestamp"] if timeline else None,
        "last_timestamp": timeline[-1]["timestamp"] if timeline else None,
        "by_severity": dict(Counter(event["severity"] for event in timeline)),
        "by_service": dict(Counter(event["service"] for event in timeline)),
        "timeline": timeline,
        "incident": {"candidate_service": candidate,
                     "evidence_ids": [event["event_id"] for event in timeline
                                      if event["service"] == candidate and event["severity"] in ("ERROR", "FATAL")]},
    }
