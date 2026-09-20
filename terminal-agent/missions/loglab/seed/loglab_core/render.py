"""A human report must retain the IDs behind the incident hypothesis."""


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def markdown_report(report):
    incident = report["incident"]
    lines = ["# Incident report", "",
             "Total events: %d" % report["total_events"],
             "Duplicate events: %d" % report["duplicate_events"],
             "Malformed lines: %d" % report["malformed_lines"], "",
             "## Investigation candidate", "",
             "Hypothesis: %s. This is an investigation lead, not a proven root cause." % cell(incident["candidate_service"] or "none"),
             "Evidence IDs: " + ", ".join(cell(item) for item in incident["evidence_ids"]), "",
             "## Timeline", "",
             "| Time (UTC) | Event ID | Service | Severity | Message |",
             "| --- | --- | --- | --- | --- |"]
    for event in report["timeline"]:
        lines.append("| " + " | ".join(cell(event[key]) for key in ("timestamp", "event_id", "service", "severity", "message")) + " |")
    return "\n".join(lines) + "\n"
