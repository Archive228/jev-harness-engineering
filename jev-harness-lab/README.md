# Jev Harness Lab

Three small tools from the article: a report on confirmed requirements, the selection of the next diagnostic, and a bounded repair loop. Also included: the first request with Choice, Score and Noul, a decision log and replay.

**Python 3.9+, macOS or Linux. No external Python packages are needed.** Locally on Python 3.9.6, 83 tests pass. POSIX is needed to stop child processes and for the overall HTTP deadline.

First time here? Follow the [ten-minute route](../START-HERE.md): from a found defect to a repaired copy of the application and a report. [Live results](../VALIDATION.md) and the [evidence gallery](../verification/evidence-gallery.en.html) show what was actually run. The repository is private; if you do not have access, use the article archive you received with the material.

The demo works without any keys. In it, real subprocess checks execute the actual code of the small application. The "Jev" answers and the worker repair are canned in the code and marked `SYNTHETIC-DEMO-NOT-JEV`. This is a demonstration of the mechanics, not an experiment on model quality.

## Quick start

From this directory:

```bash
python3 run.py inspect --mode demo --case export-ticket
python3 run.py evidence --mode demo --case missing-evidence
python3 run.py next-check --mode demo --case missing-evidence
python3 run.py loop --mode demo --case missing-evidence
python3 -m unittest discover -s tests -v
```

Each command prints the path of its own directory under `runs/`. For a convenient name, pass `--out runs/my-run`; an existing directory is not overwritten.

- `inspect`: creates `decisions.json`, where all three answer types are visible.
- `evidence`: runs C1 and shows R1=`passed`, R2=`unverified`. C2 not having run does not count as C2 failing.
- `next-check`: code runs the mandatory C2 first. When C2 fails, Choice picks an extra diagnostic; the demo picks D2. The result is in `next-check.json`.
- `loop`: after C2 and D2 the worker fixes the request parameters; fresh C1/C2 pass. The expected demo trace: **C1 → C2 → D2 → worker → C1 → C2**. That is 5 check runs and 1 repair.

The application lives in `demo-project/app.py`. On every run it is copied into its own directory `runs/.../project`. C1 checks a match by title; C2 checks a match by description alone. The backend can search both fields from the start, but the UI passes only `title`. D1 calls the backend directly, D2 shows the parameters of the UI request. `check_runner.py` holds the checks themselves; `checks.json` holds the registry and the descriptions of their scope.

## What the report means

`passed` requires the assigned mandatory test to have run successfully against the current snapshot and the current check contract. `failed` means a real assertion failure. `unverified` means there is no fresh check, or a timeout, or a tool error (for example a syntax error when importing the application).

**C1→R1 and C2→R2 are already known to the program.** Noul judges only whether the check's text description matches the requirement, and it is saved as `scope_noul`/`scope_supported`. This is a shadow annotation: it neither raises nor lowers the deterministic acceptance status. If the API for this optional annotation is unavailable, the error is written to `scope_annotation_error` and deterministic acceptance carries on. Global limits are not ignored. In a project this small, the annotation on its own does not prove any added benefit from Jev. Its usefulness on ambiguous evidence has to be checked separately.

Every result has a command, stdout/stderr, an exit code, a duration, a project hash before and after the run, a runner hash and `contract_sha256`. The last one combines the test runner, the registry and the criteria. Changing the project or the contract makes an old check unusable for completion. The hash verifies freshness; it does not prove the authenticity of records sent in from outside.

A saved state can be supplied separately:

```bash
python3 run.py evidence --mode demo --state runs/example/state.json
python3 run.py next-check --mode demo --state runs/example/state.json
```

`evidence --state` runs no new checks: it reads the records and verifies freshness. `next-check --state` may run registered commands, and `loop --state` may also run the worker, which modifies the project it was given. Such a run uses the directory from the state; that differs from an ordinary run, which creates a new copy. If the whole run directory is moved, the relative reference to its `project/` keeps the example working.

## The real Jev

The API documentation was checked against the sources on 20 September 2026 and live requests were run: [REST API](https://docs.typesafe.ai/api), [models](https://docs.typesafe.ai/models), [Choice](https://docs.typesafe.ai/primitives/choice), [Score](https://docs.typesafe.ai/primitives/score), [Noul](https://docs.typesafe.ai/primitives/noul).

The TypeSafe key is passed through the `TYPESAFE_API_KEY` environment variable; the distributed kit contains no key. Once the variable is set:

```bash
python3 run.py inspect --mode live --case export-ticket
python3 run.py evidence --mode live --case missing-evidence
python3 run.py next-check --mode live --case missing-evidence
```

`judge.py` calls `POST https://api.typesafe.ai/v1/systemone` with Bearer authorisation. The default version is `jev-1.13.0`; change it with `--model`. The request contains `state`, `model`, `questions`. The full JSON request and JSON response are saved to `judge/judge-NNN.json`; the Authorization header is not recorded. The explicit mode and the request time are saved in the same place. On an HTTP error the status code is saved, along with the provider's safe request identifier when one is available; full headers and the error body are not recorded. There are no hidden retries.

As of 20 September, two live sets are saved: the primary one and a separately prepared harder one. Each has 18 requests, 28/28 matches with the labels, and 28 accepted decisions. The article's first request was additionally run with the Russian wording: `export`, `1.0`, `0.95`. Small author-assembled sets establish neither general accuracy nor `confidence` calibration. [Method and limitations](./live-eval-method.md).

```bash
python3 live_eval.py --out runs/my-jev-primary
python3 live_eval.py --cases fixtures/live-eval-challenge-cases.json --out runs/my-jev-challenge
```

Spend is saved from the verified API `usage`, including the counters received for a response whose `answers` turned out to be invalid. `usage_complete=false` marks a failed live request; `usage_reported_requests` and `usage_unreported_requests` separate requests with full counters from requests without them. Zero known tokens on a failure does not mean the call was free. Monetary cost is not computed from tokens without a rate and the worker's own spend.

## The tested worker: Codex CLI

```bash
python3 adapters/codex_cli.py --configure
python3 run.py loop --mode live --selector jev --case missing-evidence --worker-config worker-config-codex.json --policy policy-codex.json
python3 worker_eval.py --selector jev --out runs/my-jev-codex
```

You need Codex CLI authorisation and `TYPESAFE_API_KEY`. `worker_eval.py --selector jev` runs three tasks with pre-set defects; after each one stops, a separate independent check is run. Real requests and worker calls consume service limits.

In the saved Jev + Codex run, two defects were repaired. On the third, Jev picked D2, but a `confidence` of 0.52 came in below the threshold of 0.60: the program stopped before calling the worker and saved the broken application as broken. A copy of the state was then explicitly carried on with `selector=all`: both diagnostics, one repair, four new checks and a final acceptance of PASS. That is a separate recovery, not an automatic fallback and not a third successful completion of the first route. [All results and the source records](../VALIDATION.md).

To test the worker on its own without Jev, use `python3 worker_eval.py --selector fixed --out runs/my-codex-only`. The historical run from 19 September with this selector completed three tasks out of three; it is saved separately. See [the Codex setup](./codex-worker-setup.md).

## Worker: an executable command with an explicit protocol

The demo worker changes one line: `fields=["title"]` becomes `fields=["title", "description"]`. It is not a coding model. In live mode a separate adapter is plugged in:

```bash
python3 run.py loop --mode live --task task.md --worker-config worker-config.example.json
```

First replace the path in the example config with the path to your own adapter. The config contains an `argv` array; no shell is used. The command is started with `cwd` set to the project directory. One JSON object arrives on stdin:

```json
{
  "task": "Search must match title OR description...",
  "project": "/absolute/path/to/run/project",
  "feedback": {
    "evidence_report": {"criteria": []},
    "diagnostics": []
  },
  "iteration": 1
}
```

The adapter calls the coding agent of your choice, changes the project files and returns **one JSON object on stdout**:

```json
{"claim": "Expanded the search request to include description."}
```

All technical logs go to stderr. The claim is recorded separately and is never counted as a test result. The exit code must be 0. Invalid JSON, a non-zero code or a timeout each stop the loop. The `TYPESAFE_API_KEY` key is removed from the worker's environment; the worker's own credentials stay in the environment when they are needed.

The project directory sets the working directory, but it is not an OS sandbox by itself. The coding agent's permissions are limited by its adapter and environment. The `adapters/claude_code.py` added alongside is described in the article; the generic protocol does not require Claude specifically.

### The ready-made Claude Code adapter

You need Claude Code >=2.1.248, `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY`. The adapter uses bare/restricted mode, Read/Edit only, up to 6 turns and up to $1 on the CLI limit per attempt. A real live run has not been tested.

```bash
python3 adapters/claude_code.py --configure
python3 run.py loop --mode live --case missing-evidence --task task.md --worker-config worker-config-claude.json --policy policy-live.json
```

`--configure` has to be repeated after the directory is moved: it records the absolute paths of the current installation.

## Limits and stopping

`policy.json` sets a maximum of 2 repairs, 10 checks, 10 judge calls and 120 seconds in total; separately 10 seconds per check, 20 seconds for HTTP and 90 seconds for the worker. Before an action, the smaller of its own timeout and the remaining total time is used. The API is bounded by an overall request deadline; on a worker or check timeout the whole process group is stopped. A project that did not change after a repair stops the loop with `no_new_evidence_or_source_change`.

If Choice returns `none_suitable` or insufficient `confidence`, the program stops. An API error in the Choice router also saves the facts and stops the selection. A failure of the optional Noul is noted in the report, but on its own it does not change acceptance. The model can only pick an ID from the registry, never an arbitrary command. `confidence` and the probability of the chosen option are different fields: in the live stop, D2 had a probability of 0.68 at a `confidence` of 0.52.

```bash
python3 run.py loop --mode demo --case correct
python3 run.py loop --mode demo --case stalled
```

`correct` completes with no repairs. `stalled` saves the C2 failure and stops after the project did not change. Exit code 0 means the command ran successfully (for `evidence` that means the report was created, not necessarily that the requirements passed); 2 means a bounded stop or a replay divergence; 1 means an input configuration error before the run started. Always check the outcome against `result.json` as well.

## Comparison with simple rules

```bash
python3 run.py loop --mode demo --selector fixed
python3 run.py loop --mode demo --selector all
python3 evaluate.py --out evaluation-local
```

`fixed` picks D1; `all` runs both D1 and D2. Both skip the shadow calls and work entirely without Jev. `jev` uses the Noul annotations and Choice. The `evaluate.py` matrix runs three authored cases × three policy variants; after each stop, separate assertions check extra search strings. These results are not fed back to the worker or the selector. The report is `evaluation.json`.

That is nine runs of the integration mechanics against purpose-written fixtures. The repair is deterministic, so the matrix does not measure the benefit of picking D1 over D2. You cannot conclude from it that Jev is better, faster or cheaper. Such a conclusion needs real saved states, a held-out sample, a real worker, repeated runs and a comparison at an equal budget. Saving the final outcome does not by itself make the oracle exhaustive.

## Replay

```bash
python3 run.py replay --run runs/example --policy policy.json
```

Replay repeats only the programmatic decisions against the saved contexts and answers. It calls nothing and edits nothing. At the first differing action it prints `diverged` and ends: the observations after that point belong to the earlier route. This is not a full counterfactual run. To see a divergence, copy `policy.json`, reduce `max_checks` to 1 and point the run at the new copy. Changing `scope_threshold` alone may not change any action, because Noul is shadow-only here.

## Carrying this into your own project

Edit the requirements in `task.md`, `CRITERIA` in `evidence.py`, the registered checks and their descriptions, `check_runner.py`, the fixtures and the independent oracle in step with each other. A new `--task` on its own does not change the program's criteria. As it stands this is a small teaching contract of two checks, not a universal certification of a project.

It helps to first attach Jev in shadow mode to real ambiguous cases, review the errors, and only then let its choice influence actions. The unit and integration test suite covers unknown and stale evidence, a changed contract, tool errors, `none_suitable`, `confidence`, limits, HTTP failures, a real fixture repair and the stopping of child processes.
