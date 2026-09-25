# LogLab: a checkable incident analysis

Repair a small Python CLI. The input is JSONL, one object per line. The output is JSON for automation and Markdown for the engineer on duty.

```sh
python3 loglab.py fixtures/incident.jsonl --json reports/incident.json --markdown reports/incident.md
```

Python 3.9+ is required and there are no external dependencies. Four defects were left in the project deliberately. You may change the implementation and add your own tests. Acceptance lives outside the working folder.

## Input and the exact rules

Required non-empty string fields: `event_id`, `timestamp`, `service`, `severity`, `message`. `timestamp` is ISO 8601 with an explicit time zone; `Z` is allowed. Supported levels: DEBUG, INFO, WARN, ERROR, FATAL. Case is ignored, `warning` means WARN, `err` means ERROR. An unknown level, a missing field, an invalid date, a date without a zone, or anything that is not an object makes the line invalid.

Empty lines are skipped and do not count as errors. Any other invalid line increments `malformed_lines` without stopping the analysis. Validation runs before deduplication. For a repeated `event_id` the first valid event is kept, and each one after it increments `duplicate_events`. The counters and the timeline count unique valid events only.

Sort events by their real moment in time, then by `event_id` when those are equal. Write times in JSON in UTC, exactly as `YYYY-MM-DDTHH:MM:SS.ffffffZ`. When the set is empty, `first_timestamp` and `last_timestamp` are null.

## The JSON contract

- `total_events`: the number of unique valid events.
- `duplicate_events`, `malformed_lines`: separate integer counters.
- `first_timestamp`, `last_timestamp`: the bounds of the normalised timeline.
- `by_severity`: counts for the normalised levels that are present, and no others.
- `by_service`: the event count for each service.
- `timeline`: a list of objects carrying the original `event_id`, `service` and `message`, and the normalised `timestamp` and `severity`.
- `incident.candidate_service`: the service with the most ERROR or FATAL events; on a tie the first alphabetically; null when there are no errors.
- `incident.evidence_ids`: the event_id of every ERROR or FATAL event of the chosen service, in timeline order; an empty list when there is no candidate.

The Markdown must carry the heading `# Incident report`, the total, duplicate and malformed numbers, a `## Timeline` section, every unique event_id, the candidate's name and its evidence_ids. State explicitly that the candidate is a `Hypothesis` rather than a proven root cause. Escape `|` inside the content of a Markdown table.

The CLI creates the parent directories of its output files and exits with code 0 after a successful analysis, including on empty or partly corrupted input. Both output paths are required. A non-zero code is acceptable on a system read or write error.

## What to deliver

A working implementation, your own regression tests, and `reports/incident.json` plus `reports/incident.md` for the mixed example provided. You can run the command first and watch it actually fail, then fix one property at a time.
