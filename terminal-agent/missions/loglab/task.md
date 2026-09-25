Repair the LogLab CLI, an incident analyser that reads JSONL. It should turn a dirty stream of events into a trustworthy timeline and two readable artifacts. The implementation currently contains several defects: time ordering, duplicates, invalid lines and severity levels.

Read README.md. Keep the command `python3 loglab.py INPUT --json REPORT.json --markdown REPORT.md` and the JSON contract it describes. Fix the implementation across several files, add your own regression tests, and run them. Produce `reports/incident.json` and `reports/incident.md` from `fixtures/incident.jsonl`, then briefly explain the defects you found and the result.

Acceptance is performed by an external check on separate inputs. Correct exit codes, final counters and actual event_id values matter more than convincing prose. Do not present the service with the highest ERROR count as a proven root cause: it is only a candidate for investigation. No third-party packages and no network requests.
