# What you get in ten minutes

You will run a small repair loop over search. The application has a defect: search finds a word in the title but misses it in the description. At the end you get a repaired copy of the application, a report on every requirement, and a log explaining why the program carried on or stopped.

The first run needs Python 3.9+ and macOS or Linux. You do not have to install Python packages, obtain keys or connect a coding agent. In this demo the tests really do execute the code, while the Jev answers and the worker repair are set in advance. Live API runs come as the next step.

## 1. Open the lab

Download the repository archive you have, unpack it and go into the `jev-harness-lab` directory. If you have access to the GitHub repository, you can use the `git clone` from the README.

Every command below runs **from `jev-harness-lab`**. The `runs/reader-*` directories have to be new: a repeat run with the same `--out` will ask you to choose another name.

## 2. See the difference between "unverified" and "broken"

```bash
python3 run.py evidence --mode demo --case missing-evidence --out runs/reader-evidence
cat runs/reader-evidence/evidence-report.md
```

In the report: R1 is `passed`, R2 is `unverified`. R1 stands for search by title; R2 for search by description. The program ran only C1, so it draws no conclusion about R2 yet. A report created successfully does not by itself mean the application works.

## 3. Run the repair and check the result

```bash
python3 run.py loop --mode demo --case missing-evidence --out runs/reader-loop
cat runs/reader-loop/evidence-report.md
```

Expected outcome in the terminal: `status: complete`, `checks_executed: 5`, `worker_iterations: 1`. In the final report both requirements are `passed`.

The order of actions: C1 checks the title → C2 finds the defect in search by description → D2 shows that the interface sends only the title field → the worker adds description → fresh C1 and C2 pass.

See what changed:

```bash
diff -u demo-project/app.py runs/reader-loop/project/app.py
```

`description` appears in the `fields` parameter. Exit code 1 from `diff` here means the files differ, which is expected.

Three useful files from your run:

- `project/app.py`: the repaired copy of the application. The original `demo-project/app.py` is left unchanged.
- `evidence-report.md`: the result per requirement for the current code.
- `events.jsonl`: the log of programmatic decisions; `judge/` holds the judge requests and answers separately.

## 4. Confirm that the loop knows how to stop

```bash
python3 run.py loop --mode demo --case stalled --out runs/reader-stalled
```

This worker does not change the project. Expect `status: stop`, the reason `no_new_evidence_or_source_change` and exit code 2. The program neither declares the task finished nor tries to repair it forever. Check the saved `runs/reader-stalled/evidence-report.md`: R2 stays `failed`.

## 5. Replay the decisions from the log

```bash
python3 run.py replay --run runs/reader-loop --policy policy.json
```

Expect `status: matched`, `decisions: 7`. This rechecks the selection logic against the saved data. No new tests, no model and no worker run here.

## How to turn the example into your own tool

Start with your own requirements and executable checks. Then pick one narrow role for Jev: which diagnostic to run after a failure has already been found, for example. The model picks the ID of a registered action; code sets the permitted commands, the limits and the completion conditions. Only after that do you connect a real worker.

Changing `--task` alone does not move the lab onto a new project. `task.md`, `CRITERIA` in `evidence.py`, `checks.json`, `check_runner.py`, the fixtures and the final oracle change together. The detailed order is in the "Carrying this into your own project" section of the lab README.
