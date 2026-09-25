# JEVIS: an agent in your terminal

Start with one sentence: "I want something useful about crypto". JEVIS helps you pick the result, asks the questions it needs and prepares a plan you can read. After **Start work** it creates and fixes files, runs commands and shows the result together with the checks. Jev is the typed-decision mechanism inside JEVIS; the conversation, the plan and the record are saved locally.

This is the runnable product that goes with the article **Jev + Harness Engineering**. A normal start opens an empty chat and waits for your message. **Enter** or **Discuss** sends the whole text. **Ctrl+J** adds a new line; Shift+Enter also works if the terminal passes that combination through. A paste keeps every paragraph and sends nothing by itself. Ctrl+D remains an additional way to send.

## First run

You need macOS or Linux, Python 3.9+, the [Codex CLI](https://developers.openai.com/codex/cli/) installed and signed in, and a [TypeSafe](https://console.typesafe.ai/keys) key. Download the whole repository kit: the terminal agent also uses the client from the neighbouring `jev-harness-lab` directory.

From the `terminal-agent` directory:

```bash
./setup.sh
./jev --doctor
./jev
```

`setup.sh` creates `.venv` and installs the pinned dependencies. `--doctor` checks the versions, whether the key is present and the path to Codex, without calling any model. If the environment is already installed, `./jev` is enough.

To sign the worker in, run `codex login`. If the binary sits outside `PATH`, you can point `CODEX_WORKER_BIN` at it. On macOS the Codex bundled with the ChatGPT application is supported too.

The TypeSafe key can be passed without writing its value into the shell history:

```bash
read -s TYPESAFE_API_KEY
export TYPESAFE_API_KEY
./jev --doctor
./jev
```

After `read`, paste the key and press Enter; the input is not shown. The alternative is a local `.env.live` one level above `terminal-agent`: only the `TYPESAFE_API_KEY=…` line is read, and the file is not executed as shell code. The key is not part of the repository and is not passed to the Codex process through the environment.

Codex uses your current model and CLI sign-in. Jev is pinned to `jev-1.13.0`. Running the agent spends the available limits of those services. The `off` mode needs no TypeSafe key; the Codex sign-in is still required.

## From an idea to a defined task

After `./jev` you can simply write:

```text
I want something useful about crypto that I can use myself afterwards.
```

The agent then helps you state the work:

1. **Refinement.** If the result is not clear yet, a compact round of one to three related questions appears. For a full task JEVIS usually establishes the result, the main input and the main success criterion; a second round is available when needed. The options carry short explanations and a recommendation; you can always write your own answer. The questions depend on the request and on the project context available. A clear task can go straight to the plan.
2. **Checking the answers.** You can go back and change a choice. A highlighted option does not count as an answer yet. A multi-line paste is kept whole.
3. **The plan.** It shows the goal, the specific files or other results, the steps, the checks to come, the limits and the assumptions. The **Agent request** tab holds the exact task for execution.
4. **Refine or start.** The **Refine** button takes a correction in ordinary language and creates a new version of the plan. **Start work** runs exactly the version you reviewed.
5. **The result.** The conversation keeps the answer, the changed files and the checks that actually ran. The Jev and command details can be expanded separately.

![Refining an ordinary request](./verification/screenshots/guided-questions-browser.png)

The planner runs through Codex in read-only mode and receives a limited context from the harness. It does not edit the project and does not call Jev to write the questions. Simple requests to explain something get an answer without a mandatory round of questions and a plan.

![The plan with its result, steps and checks before the start](./verification/screenshots/guided-plan-browser.png)

**Escape** or **Later** closes the form. The answers are saved; you can carry on through **Task**, **F5**, `/brief` or `/plan`. After a restart an unfinished discussion is restored without anything running automatically. If the project changed after the plan was prepared, the application asks you to update it.

The "How we check" items are criteria for later, not test results. They are passed to the worker; the independent contract is set separately through `jev-checks.json`.

For a task that is already precise you can pick `/direct` or start `./jev --direct`: the next messages go straight into the execution loop. `/guided` brings the discussion back. Switching the mode starts nothing by itself.

## Start with the crypto task

The clearest first run is **Crypto Ledger**: a small CLI that accounts for trades from a CSV, with a contract known in advance. The agent gets a working copy of the project with defects in it. Its task is to fix the calculations, run the checks and save the report.

```bash
./jev --mission cryptolab
```

1. Press **Insert an example task** or **F2**: the task of this particular mission is pasted into the editor.
2. Read it and press **Enter** or **Discuss**.
3. Look at the plan and press **Start work**. The mission already has a detailed task and checks, so extra questions may not be needed.
4. Watch the real commands and results; the tool cards expand on a click or Enter.
5. Press **Files** to read the fixed code, the saved diff and `report.json`.

The program handles synthetic trades: buys and sells, fees in USDT, exact amounts through `Decimal`, repeated IDs, different time zones and corrupted rows. It computes cash flow and the remaining quantity. This is not PnL and not a trading recommendation; no exchange keys and no real money are needed.

Seven tests are set **before the agent starts**, and the original version passes only one. The existing `tests/` and `jev-checks.json` are fixed by hashes: they cannot be rewritten to obtain a green result. In the harness panel this is one check command; its detailed stdout shows the results of the seven tests inside it. The expected result of the mission is a fixed CLI, a report and the exact command that produces it, confirmed by the saved checks.

The original task and the project: [examples/crypto-ledger](./examples/crypto-ledger/). `task.txt` there is the prompt of that recorded run, kept in the language it was run in, and `task.en.txt` is the same task in English, which is what the mission uses now. This run is not a recording: the model really does work on a fresh copy of the files. On a failure you see the failure, not a prepared success put in its place.

Once it has run you can write: "Explain where the BTC cash flow in the report comes from" or "Add a filter by symbol and separate tests for it". A new requirement can fall outside the original seven tests, and the old contract does not by itself prove that it is met.

## You can give it your own task

```bash
./jev
```

You can start with a short idea and refine it together. If the requirements are already clear, paste the whole thing:

```text
Build a Crypto Detective CLI in Python with no external libraries.

It reads a transaction CSV with the fields tx_hash, timestamp,
from_address, to_address, token, amount. Build an ASCII graph,
find circular transfers and chains of up to three hops.
For every observation give the specific tx_hash values.
Do not add different tokens together; sum amounts through Decimal.

Create clearly labelled demonstration data, Markdown and JSON
reports, and tests. Really run the program and the checks.
Keep observable links separate from hypotheses: transfers do
not prove that wallets share an owner.
At the end give me the command to analyse my own CSV.
```

Here the agent creates the program from scratch. The tests it writes itself are useful, but they differ from the independent contract that Crypto Ledger sets in advance. The interface shows that difference in the final status.

Working on an existing project:

```bash
./jev --project /absolute/path/to/project
```

Once the plan is accepted the agent can change the project you chose. To get acquainted with the hard write ban:

```bash
./jev --project /absolute/path/to/project --mode plan
```

## The conversation, the tools and the details

Most of the screen is the conversation, on a dark background with a pink accent. The top line now says **JEVIS** outright. On the right a small log of live stages and commands stays visible; the tabs next to it open the decisions, the checks and the full events. The compact navigation opens **Task**, sessions, files, JEVIS, logs and the menu. **New** creates a separate session with a new workspace; the previous conversation and draft stay saved. Sessions and modes can be switched between turns.

Jev decisions, commands and checks are collected in **Activity**. After a successful finish that group collapses and the final answer stays separate. A click on the header or **Ctrl+O** expands the last group. If the turn ended in an error, a cancellation or a question for the user, the details stay open.

Answers support Markdown and code blocks. The **↓ Answer** button returns to the end of the conversation. **Files**, **Copy** and **Export** sit next to it. **Copy** first sends the text to the terminal clipboard and then always saves an exact full copy to `exports/answer.txt` inside the current session: if the terminal supports neither OSC 52 nor the system clipboard, the path is still shown in a notification. **Export** saves the conversation as Markdown.

![The result after discussing and executing the task](./verification/screenshots/guided-result-browser.png)

Each tool has one expandable card: the start and the end of a single call both update it. The header shows a readable action type and the actual exit code; below it you see the number of lines and the beginning of the output. A click on the card opens the full saved command and a limited stdout preview. The current stage is shown as a short line; the counters are in the details.

**JEVIS** or **F6** opens the details: the graph and Jev's answers with their probability distributions, the checks and files, the event log. The panel is hidden at start. In a narrow window it takes over the conversation area while keeping the editor reachable. **Logs** or **F3** opens the events tab directly: it is a limited on-screen preview, up to 4000 lines, and long payloads are shortened. The full sequence of events is in `events.jsonl` on disk. The current status distinguishes discussion, a ready plan and execution. On a restore it says that this is saved history.

The message field grows as you paste text, wraps long lines and scrolls. The **↕** button or **F4** expands it to nearly the whole screen. **⌘⌫** deletes the current line, and **Ctrl+U** is the fallback for terminals that do not pass Command through. The limit for a message and for a draft is 20,000 characters; a request that is too long stays in the editor. The draft is saved separately for each session and restored without being sent. While the agent is working, a **Stop** button sits next to the editor. The **Discuss** and **Execute** buttons separate two decisions: the first turns on the questions and plan acceptance, the second grants the right to change files. Discussion is on by default; if the plan is already written, pick **Straight to the task** at the bottom.

- **Enter** sends the whole message; **Ctrl+J** makes a new line. Shift+Enter adds a line if the terminal supports it. **Ctrl+D** also sends.
- **F1 / Ctrl+P** finds a command; **F2** pastes the example without running it.
- **F3** events; **F4** the large editor; **F5** questions and plan; **F6** Jev details.
- **Ctrl+O** expands or collapses the last Activity group.
- **Ctrl+S** saves the real current screen as SVG.
- **Ctrl+C** stops the active task, and quits while nothing is running.

Commands are typed in the editor too and sent with Enter:

- **`/brief`**, **`/plan`** open the unfinished questions or the ready plan. `/plan` does not change write permissions.
- **`/guided`** discusses the request before execution; **`/direct`** executes the next requests without the preceding questions and plan acceptance.
- **`/new`** starts a new chat with a separate workspace.
- **`/sessions`** finds a saved task and carries on with it. The current draft is saved, and the draft of the task you pick is restored.
- **`/files`** opens the files of the workspace and the saved changes. A historical diff is shown only where it really was recorded; the current file may already differ.
- **`/export`** saves the conversation as Markdown inside the session directory.
- **`/status`** shows the settings, the calls and the counters; **`/help`** shows the help.
- **`/stop`** stops execution; **`/clear`** clears the screen while keeping the history on disk; **`/bottom`** jumps to the end of the conversation; **`/quit`** exits.

Jev and worker tokens are available through `/status` and the `meters` events. These are the providers' counters, not a money cost. On a cancellation, or when data is missing, the usage is marked as incomplete.

## How Jev works inside the agent

**Jev makes bounded decisions. Codex writes the questions, the plan, the text and the code. The Python harness governs the transitions, the execution and the checks.** Jev is not a generator of conversational answers and does not steer every individual shell command inside a Codex call.

Before execution a separate Codex call returns a structured answer: the questions, the plan or a plain explanation. The harness validates the format and saves the answers and the plan version. At that stage the Jev call counter is zero. After **Start work** the usual loop with the `auto` + `assist` settings goes like this:

1. **Jev route.** Choice picks `implement`, `inspect` or `answer`. That decides whether the worker may change files. Below a confidence of 0.25 Python picks reading.
2. **Context from the real files.** A local search selects up to five fragments with their paths, line numbers and SHA-256. If there are at least two candidates, Jev receives their text and answers a Noul question about the relevance of each. In `assist` the order of those answers affects which three fragments go to Codex. With an empty workspace that Jev call is not needed.
3. **Codex.** It receives the request, the latest messages, the selected fragments and the results of the previous checks. It reads the current files, produces an answer and runs tools. The terminal displays the events as they arrive.
4. **Python checks.** A contract registered in advance runs before the changes and after the attempt. Without a contract the harness can discover and run the project's unittest tests. It checks the exit code, that the contract is unchanged and that the file snapshot is current.
5. **Jev review.** Choice proposes `finish`, `improve` or `ask_user`; Noul judges how well the result matches the request. The input is the Codex claim, the list of changes and the observable checks, not the whole source code by default.
6. **Retry or finish.** A failing check blocks success whatever Jev thinks. If there is room to carry on, Jev triage classifies the actual failure and the next attempt gets a limited diagnostic hint. That is a hypothesis about the category of the error, not a proven root cause.

The probabilities belong to specific Jev questions. They do not mean "the whole code is correct with probability 99%". The interface has no invented thinking and no painted progress: the visual states come from the saved events.

## Modes that really change behaviour

The execution and Jev modes can be chosen at start or changed between turns. They are saved together with the session. They are separate settings from `/guided` and `/direct`: discussing the task does not lift the execution limits.

**`/mode auto`** is ordinary execution. In `assist` the permissions follow the Jev route: `implement` uses `workspace-write`, while `inspect` and `answer` use `read-only`.

**`/mode plan`** is always `read-only`: study the project, explain something or draw up a plan. A Jev decision cannot grant write access. The harness does not run the project's acceptance commands in such a turn. To implement a prepared plan, switch to `/mode auto`, open `/brief` and press **Start work**.

**`/jev assist`** applies Jev's answers: the routing, the context ranking, the assessment of the result and suitable diagnostic hints. This is the default.

**`/jev observe`** calls Jev and saves its answers, but does not use them for the route, the context order, the retries or the triage hints. The feed marks this as "the decision is not applied". Python uses the local context order and the check rules. In `auto` the worker gets write permissions but must change files only when the user asks; for a hard write ban pick `plan`.

**`/jev off`** makes no Jev API calls. Codex, the local search, the checks, the history and the interface all remain; the Python rules are the same as in `observe`. This is how you compare behaviour, or work without a TypeSafe key.

**`--worker codex|claude`** chooses who does the work. The choice is saved in the session, so `--resume` carries on with the same worker. Codex runs in the OS kernel sandbox with the network switched off. Claude Code has no such mechanism, so the "no network and no package installation" guarantee holds in another way: it is given no Bash, and `--restricted` ignores your `~/.claude/settings.json` and locks the file tools into the workspace. Verified by running it: an attempt to write a file outside the workspace is rejected. In both cases the checks are run by the harness, not by the worker.

```bash
jevis --worker claude            # do the work through Claude Code
jevis --worker codex             # through Codex (the default)
jevis --doctor                   # shows which workers were found
```

Claude Code is usually not in PATH: it sits inside the desktop application, and the agent finds it by itself. The path can be set through `CLAUDE_WORKER_BIN`. Its sign-in is separate from the application: `claude auth login`, on a subscription.

**`--demo`** runs a full turn without Codex and without a TypeSafe key. Only two network stretches are replaced: the judge answers according to the schema of the questions asked, and in place of Codex a demo worker creates two small real files. The route, the context selection, the running of the checks and the completion rules are the working path, not a recording. Every synthetic answer is marked: the model `SYNTHETIC-DEMO-NOT-JEV`, zero usage and a `synthetic` field in the event, so a demo run cannot be mistaken for a measurement. The demo worker writes files, so `--demo` does not combine with `--project`.

```bash
./jev --mode plan --jev-mode assist
./jev --jev-mode observe
./jev --jev-mode off
./jev --demo                        # see the whole turn without installing Codex
./jev --demo --mission cryptolab    # demo on a contract: a stop instead of false acceptance
```

In `assist` a failure of the mandatory route or review stops the turn. Context ranking and triage are optional hints: when they are unavailable the reason is shown and the Python policy applies. In `observe` a Jev failure does not switch the worker off either. Model answers are never replaced with a synthetic success.

## What counts as a finished result

**Answer prepared** means a reading or explaining turn is finished. **Result prepared** means an artefact was created, but there is no independent registered contract. Even if the worker's own tests passed, that is not independent acceptance.

**Contract checks passed** means the checks registered in advance passed on the current snapshot. The statement is limited to their requirements: it does not prove the absence of every error and does not automatically cover later wishes.

For your own project you can add `jev-checks.json` in advance:

```json
{
  "checks": [
    {
      "id": "regressions",
      "title": "Existing regression tests",
      "argv": ["python3", "-B", "-m", "unittest", "discover", "-s", "tests", "-v"]
    }
  ]
}
```

This is trusted user configuration. The arguments are run without shell interpolation. When a session is created, the commands and the hashes of the existing `tests/` files, of the configuration and of the file arguments are fixed. Changing those files forbids acceptance; to change the contract deliberately, create a new session.

Without a contract the harness looks for `tests/test*.py` or `test*.py` in the root and runs unittest with a note that the worker may have created the tests. A `Ran 0 tests` result is not accepted as a passing check.

## History and results on disk

Every new start creates a separate session; without `--project` a workspace appears inside it:

```text
.sessions/<session-id>/
  workspace/                created and fixed files
  session.json              history, modes, contract
  draft.txt                 the unsent draft
  events.jsonl              the real events in order
  screenshots/              Ctrl+S snapshots
  turn-001/
    request.json            the request and the modes of this turn
    context.json            candidates, fragments and the context choice
    jev-*/                  Jev requests and answers
    worker-*/               the task, the Codex JSONL, the final answer
    *-checks.json           the actual running of the checks
    attempt-*-diffs.json     saved changes and hashes
    result.json             the outcome and the counters
```

The project directory is shown in the header and in `/status`. Sessions, keys and `.venv` are not included in Git. The log holds your requests, command output and code fragments; export exactly the material you want to share.

```bash
./jev --resume last                 # carry on with the last session
./jev --resume SESSION-ID           # pick a session by ID
./jev --list                        # list sessions as JSON, no models
./jev --resume last --export        # export to Markdown, no models
./jev --replay last                 # recompute the session's decisions, no models
./jev --prompt 'Study this project' # fill the editor, do not send
```

`--replay` reads only `events.jsonl` and recomputes every recorded decision twice: under the thresholds that were in force at the time of the turn, and under today's. The first shows that the decision code has not changed behaviour on the real history; the second shows what a change of threshold would have done. No workspace is needed for this, there are no Jev or Codex calls, and exit code `2` means a divergence. The thresholds and the policy version live in `jev_agent/decision.py` and are written into the `result.json` of every turn.

`--resume` does not combine with `--mission` or `--project`: the session already has a workspace. For integrations there is an explicitly non-interactive `./jev --run 'task'`: it skips the questions, runs one turn straight away and prints JSONL. A plain `./jev` waits for input and starts with the discussion; `./jev --direct` opens a chat with direct execution.

Unfinished questions, the answers and the plan version live in `brief.json` inside the session. `intake/round-NNN/` keeps the context, the structured answer, the counters and the snapshots of the preparation. The execution request and the results sit separately in `turn-NNN/`. That lets you compare the original sentence, the agreed task and the actual result.

## Execution limits

One turn is limited to fifteen minutes and three Codex attempts. A single attempt is limited to eight minutes, and a single check command to thirty seconds. A Jev HTTP request is limited to twenty seconds, and its process to twenty-five. A cancellation terminates the group of child processes; changes already made stay on disk.

The context is a limited initial sample: up to 512 files and 4 MiB of reading, a file up to 64 KiB, up to five fragments of 1600 bytes each, of which three go to the worker. Hidden files, ignored files, files that look like secrets and symbolic links are excluded. The absence of a match does not prove the absence of the code you need: Codex can read further into the project. The project snapshot is limited to 5000 files; for a large monorepo, pick a narrower directory.

A file preview is limited to 64 KiB. A diff is saved for a limited set of safe text files: up to ten changes per attempt, up to 64 KiB per diff and 256 KiB in total. If the original text is missing or the hash did not match, the interface reports the diff as unavailable and does not reconstruct it from guesses.

The thresholds of 0.25 for route, 0.60 for review and 0.50 for Noul are settings of this harness, not universal guarantees. In `assist` the triage diagnostic hint is applied only when confidence is at least 0.55 and the probability of the chosen category is at least 0.65.

Codex has its network tools, web search and privilege escalation switched off; the request to the worker also forbids publishing, installing dependencies and changes outside the chosen project. Local checks are run separately by the harness, so register only trusted commands. The context limits and the secret filters are not a general safety guarantee for an arbitrary project belonging to somebody else.

## An extra example and checking the kit

`./jev --mission loglab` creates an incident analyser with four defects: time zones, repeated events, corrupted rows and severity. The Insert an example task button or F2 pastes the task; Enter sends it to the discussion, and **Start work** runs the accepted plan. The external oracle holds six checks and is not copied into the workspace; the original project passes one.

To check the terminal agent itself:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

In the automated tests the models are replaced explicitly; the subprocess checks start real processes and verify that children are cancelled. [Verification of discussion and execution](./verification/guided/README.md) holds the record of the new chain. [Verification v2](./verification/v2/README.md) and [verification of the previous pink interface](./verification/ui-pink/README.md) keep the historical results. Restoring an earlier live run in the new interface does not mean the models were called again.

The new version really does adapt the question-state code from OpenCode, the recommendation functions from Hermes and the planning instructions from open-source Codex. This is not a pile of unused fragments: `IntakeController` keeps the versions and drafts, `question_state` governs the transitions, `QuestionsScreen` and `PlanScreen` give the person control, and JEVIS starts the worker only after the current version is accepted. The original files, licences and changes are kept in `vendor/`; the runtime uses the adaptations for Python and Textual. More detail: [where the code came from](./research/ATTRIBUTION.md), [the study of the questions and the interface](./research/interaction-intake.md), [Hermes](./research/hermes-intake.md), [Codex](./research/codex-intake.md).

The architecture of the first version: [RESEARCH.md](./RESEARCH.md). The historical audit of PiJev, Pi, OpenCode and Crush: [upstream-audit.md](./research/upstream-audit.md). These materials record the state of the versions studied and do not replace the current instructions for running the agent.
