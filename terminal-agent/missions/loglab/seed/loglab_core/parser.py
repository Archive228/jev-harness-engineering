"""Load JSONL events and normalize their fields."""
from datetime import datetime, timezone
import json


def parse_events(text):
    events = []
    malformed = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        for field in ("event_id", "timestamp", "service", "severity", "message"):
            if not isinstance(event.get(field), str) or not event[field].strip():
                raise ValueError("Missing event field: " + field)
        instant = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError("Timestamp must have a timezone")
        event = dict(event)
        event["timestamp"] = instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        event["_sort_key"] = json.loads(line)["timestamp"]
        level = event["severity"]
        event["severity"] = level if level in ("DEBUG", "INFO", "WARN", "ERROR", "FATAL") else "INFO"
        events.append(event)
    return events, malformed
