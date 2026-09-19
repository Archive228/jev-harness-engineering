# Codex CLI as the correction worker

The harness sends one JSON request to the adapter. Codex reads and repairs the copied `app.py`; the adapter returns `{"claim": "..."}`. The harness then executes its own acceptance checks. A worker's message never marks a requirement as passed.

## Setup

Use a locally installed Codex CLI with an existing login. The adapter uses the configured default model and the CLI's existing authentication. It never reads or copies credential files. Check the installation:

```bash
codex --version
codex login status
python3 adapters/codex_cli.py --configure
```

When the executable is not on `PATH`, pass it explicitly:

```bash
python3 adapters/codex_cli.py --configure \
  --codex-bin /absolute/path/to/codex
```

This writes `worker-config-codex.json` with absolute paths for this machine, plus `policy-codex.json` with a 105-second supervisor timeout and a 300-second run budget. Regenerate the worker config after cloning or moving the project.

## Run with Jev

With `TYPESAFE_API_KEY` already set in the environment:

```bash
python3 run.py loop --mode live --case missing-evidence \
  --worker-config worker-config-codex.json \
  --policy policy-codex.json
```

The run uses the copied fixture under `runs/<run-id>/project`. This adapter intentionally rejects imported projects outside `runs/`; adapt and review the edit scope before using it on a real repository. It leaves the original `demo-project/app.py` untouched.

## Execution contract

The adapter invokes `codex exec` with `workspace-write`, `approval_policy="never"`, disabled tool-network access and web search, and no subagents. The noninteractive approval policy rejects actions requiring escalation; it does not remove the sandbox. No bypass flag is used. The prompt permits changing only `app.py`, and the adapter rejects results that modify other fixture files. These checks supplement the sandbox; they are not a general-purpose defense for running untrusted projects.

The model call has a 90-second timeout. The outer harness supervisor terminates the adapter's process group and descendants on completion or timeout, so this adapter should be invoked through `run.py`. Token counts and item counts go to stderr and are preserved in the worker event. The final text is read from `--output-last-message`; raw provider stderr and tool arguments are not copied into the report. A provider failure, malformed event stream, unfinished turn, missing final message, or edit outside scope returns a worker error.

## Contract tests

```bash
python3 -m unittest discover -s tests -p 'test_codex_adapter.py' -v
```

These tests mock the model process and exercise the adapter contract, scope, timeout, and failure handling. A model-assisted repair is a separate integration run; its actual acceptance results are recorded by the harness under `runs/`.

The flags were checked against local Codex CLI `0.155.0-alpha.9`. Their documented behavior is described in [non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security), and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
