"""Observable, cancellable child processes. No shell interpolation."""
import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time

from . import transport


class RuntimeFailure(RuntimeError):
    pass


def clean(value):
    if isinstance(value, dict):
        return {str(k): ("[redacted]" if re.search(r"authorization|api.?key|access.?token", str(k), re.I)
                         else clean(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", value)
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", value)
    value = re.sub(r"(?:apikey_[A-Za-z0-9_]+|new1_[a-fA-F0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})", "[redacted]", value)
    value = re.sub(r"(?i)(Bearer\s+)\S+", r"\1[redacted]", value)
    return value


def worker_environment():
    # Preserve CLI login and ordinary user tools, but do not inherit provider secrets.
    environment = {k: v for k, v in os.environ.items()
                   if not re.search(r"API.?KEY|TOKEN|SECRET|PASSWORD", k, re.I)}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def codex_binary():
    path = os.environ.get("CODEX_WORKER_BIN") or shutil.which("codex")
    if not path and Path("/Applications/ChatGPT.app/Contents/Resources/codex").is_file():
        path = "/Applications/ChatGPT.app/Contents/Resources/codex"
    if not path or not Path(path).is_file():
        raise RuntimeFailure("Codex CLI не найден. Установите Codex и выполните codex login.")
    return str(Path(path).resolve())


def claude_binary():
    """Claude Code ships inside the desktop app; it is usually not on PATH."""
    path = os.environ.get("CLAUDE_WORKER_BIN") or shutil.which("claude")
    if not path:
        bundles = sorted(Path.home().glob(
            "Library/Application Support/Claude/claude-code/*/claude.app/Contents/MacOS/claude"))
        # Directory names are versions; the last one sorts highest.
        path = str(bundles[-1]) if bundles else None
    if not path or not Path(path).is_file():
        raise RuntimeFailure("Claude Code не найден. Установите его или задайте CLAUDE_WORKER_BIN.")
    return str(Path(path).resolve())


async def process(argv, *, cwd, cancel_event, timeout=240, input_text=None,
                  environment=None, on_line=None, max_bytes=4_000_000):
    """Drain both pipes; a cancellation/timeout kills the whole process group."""
    if cancel_event.is_set():
        raise asyncio.CancelledError()
    started = time.monotonic()
    child = await asyncio.create_subprocess_exec(
        *[str(a) for a in argv], cwd=str(cwd), env=environment,
        stdin=asyncio.subprocess.PIPE if input_text is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        start_new_session=True, limit=2_100_000)
    buffers = {"stdout": [], "stderr": []}
    used = {"bytes": 0}
    group_terminated = False

    def kill():
        nonlocal group_terminated
        if group_terminated:
            return
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        # The waiter and both finally blocks share cleanup. Once SIGKILL was
        # delivered (or the group was already gone), do not signal its old ID
        # again: on macOS a reaped group may produce EPERM instead of ESRCH.
        # A denied first signal still propagates and leaves cleanup retryable.
        group_terminated = True

    async def read(pipe, stream):
        while True:
            line = await pipe.readline()
            if not line:
                return
            used["bytes"] += len(line)
            if used["bytes"] > max_bytes:
                raise RuntimeFailure("Вывод процесса превысил лимит; выполнение остановлено.")
            decoded = line.decode("utf-8", "replace")
            buffers[stream].append(decoded)
            if on_line:
                on_line(stream, decoded)

    async def communicate():
        readers = [asyncio.create_task(read(child.stdout, "stdout")),
                   asyncio.create_task(read(child.stderr, "stderr"))]
        async def wait_child():
            await child.wait()
            kill()
        waiter = asyncio.create_task(wait_child())
        try:
            if input_text is not None:
                child.stdin.write(input_text.encode("utf-8"))
                await child.stdin.drain()
                child.stdin.close()
            # A failed reader/parser must stop the producer immediately, including
            # when it is still writing to a now-undrained pipe.
            await asyncio.gather(waiter, *readers)
        finally:
            kill()
            for task in [waiter] + readers:
                if not task.done():
                    task.cancel()
            await asyncio.gather(waiter, *readers, return_exceptions=True)

    work = asyncio.create_task(communicate())
    cancel = asyncio.create_task(cancel_event.wait())
    try:
        done, _ = await asyncio.wait([work, cancel], timeout=timeout,
                                     return_when=asyncio.FIRST_COMPLETED)
        if cancel in done or cancel_event.is_set():
            raise asyncio.CancelledError()
        if work not in done:
            raise RuntimeFailure("Процесс превысил лимит %.0f секунд." % timeout)
        await work
        return {"exit_code": child.returncode,
                "stdout": "".join(buffers["stdout"]), "stderr": "".join(buffers["stderr"]),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2)}
    finally:
        kill()
        if not work.done():
            work.cancel()
        cancel.cancel()
        await asyncio.gather(work, cancel, return_exceptions=True)
        await child.wait()


class CodexRunner:
    async def run(self, prompt, workspace, directory, emit, cancel_event,
                  readonly=False, schema=None):
        directory.mkdir(parents=True, exist_ok=True)
        last = directory / "final.txt"
        argv = [codex_binary(), "exec", "--sandbox", "read-only" if readonly else "workspace-write",
                "-c", 'approval_policy="never"',
                "-c", "sandbox_workspace_write.network_access=false",
                "-c", 'web_search="disabled"', "-c", "agents.enabled=false",
                "--skip-git-repo-check", "--ephemeral", "--json", "--color", "never",
                "--cd", str(workspace), "--output-last-message", str(last), "-"]
        if schema:
            schema_path = directory / "schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            argv[-1:-1] = ["--output-schema", str(schema_path)]
        (directory / "prompt.txt").write_text(clean(prompt), encoding="utf-8")
        state = {"completed": False, "failed": False, "usage": None, "text": "", "error": ""}
        raw_log = directory / "events.jsonl"

        def line(stream, text):
            if stream != "stdout":
                return
            try:
                event = json.loads(text)
            except ValueError:
                raise RuntimeFailure("Codex вернул повреждённый JSON-поток.") from None
            with raw_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(clean(event), ensure_ascii=False) + "\n")
            kind = event.get("type")
            if kind == "turn.completed":
                state["completed"], state["usage"] = True, event.get("usage")
            elif kind in ("turn.failed", "error"):
                state["failed"] = True
                # Keep the provider's own words: usage limits and auth failures are
                # reported here and never reach stderr, so pointing the user at an
                # empty stderr.txt hides the only explanation there is.
                detail = event.get("error", event)
                message = detail.get("message") if isinstance(detail, dict) else None
                state["error"] = clean(str(message or detail))
                emit("tool", kind="provider_error", status="error", output=state["error"])
            elif kind in ("item.started", "item.updated", "item.completed"):
                item = event.get("item", {})
                item_kind = item.get("type", "unknown")
                if item_kind == "reasoning":
                    return  # Observable actions, not a presentation of hidden reasoning.
                if item_kind == "agent_message" and kind == "item.completed":
                    state["text"] = item.get("text", "")
                    emit("message", role="assistant", text=state["text"])
                elif item_kind == "todo_list":
                    emit("plan", steps=[{"id": str(i + 1), "title": t.get("text", ""),
                                          "completed": t.get("completed", False)}
                                         for i, t in enumerate(item.get("items", []))])
                elif item_kind in ("command_execution", "file_change", "mcp_tool_call", "web_search"):
                    emit("tool", kind=item_kind, command=item.get("command", item.get("tool", "")),
                         status=item.get("status", "running" if kind == "item.started" else "finished"),
                         output=item.get("aggregated_output", ""), exit_code=item.get("exit_code"),
                         files=item.get("changes", []), item_id=item.get("id"),
                         call_id=("%s:%s:%s" % (directory.parent.name, directory.name, item["id"])) if item.get("id") else None,
                         lifecycle=kind.split(".", 1)[1])

        result = await process(argv, cwd=workspace, input_text=prompt,
                               environment=worker_environment(), cancel_event=cancel_event,
                               timeout=480, on_line=line)
        (directory / "stderr.txt").write_text(clean(result["stderr"]), encoding="utf-8")
        if result["exit_code"] or not state["completed"] or state["failed"]:
            reason = state["error"] or clean(result["stderr"].strip()).strip()
            raise RuntimeFailure("Codex не завершил ход. " + (
                reason if reason else "Подробности: %s" % (directory / "stderr.txt")))
        text = clean(last.read_text(encoding="utf-8") if last.is_file() else state["text"])
        last.write_text(text, encoding="utf-8")
        if not text.strip():
            raise RuntimeFailure("Codex завершился без ответа.")
        return {"text": text, "usage": state["usage"], "completed": True}


class ClaudeRunner:
    """Claude Code as the worker, with the same contract as CodexRunner.

    Two differences from Codex drive every choice here. Claude Code has no
    OS-level sandbox, so the only structural guarantee of "no network, no
    installs, nothing outside the workspace" is withholding Bash; the harness
    runs the checks anyway, so little is lost. And a failed run still exits 0
    with subtype "success" - the lost-login probe proved it - so success is
    decided by ``is_error`` and the presence of a final result, never by the
    exit code.
    """

    # Only what a worker needs to read and edit. Bash, WebFetch, WebSearch and
    # Task are absent on purpose: naming them here is what grants them.
    TOOLS_WRITE = "Read,Glob,Grep,Edit,Write,TodoWrite"
    TOOLS_READONLY = "Read,Glob,Grep,TodoWrite"
    KINDS = {"Read": "read", "Glob": "read", "Grep": "read",
             "Edit": "file_change", "Write": "file_change", "NotebookEdit": "file_change",
             "Bash": "command_execution", "BashOutput": "command_execution",
             "KillShell": "command_execution",
             "WebFetch": "web_search", "WebSearch": "web_search"}

    @staticmethod
    def _command(name, arguments):
        arguments = arguments if isinstance(arguments, dict) else {}
        for field in ("command", "file_path", "pattern", "path", "url"):
            value = arguments.get(field)
            if isinstance(value, str) and value:
                return value
        return name

    @staticmethod
    def _text_of(content):
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(part.get("text", "") for part in content
                             if isinstance(part, dict) and part.get("type") == "text")
        return ""

    def _usage(self, raw):
        """Cached input is still input: a turn that reuses cache still cost it."""
        if not isinstance(raw, dict):
            return None
        output = raw.get("output_tokens")
        parts = [raw.get(name) for name in
                 ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")]
        parts = [value for value in parts if type(value) is int and value >= 0]
        if type(output) is not int or output < 0 or not parts:
            return None
        return {"input_tokens": sum(parts), "output_tokens": output}

    def _failure(self, state, result):
        """Say why in the provider's own words; the exit code says nothing."""
        final = result.get("result") if isinstance(result, dict) else None
        if isinstance(final, str) and final.strip():
            return clean(final.strip())
        # A denial names the actual obstacle; a subtype only names the category,
        # so the specific reason is offered first.
        denials = (result or {}).get("permission_denials")
        if denials:
            names = sorted({d.get("tool_name") or d.get("tool") or "?" for d in denials
                            if isinstance(d, dict)})
            return "Claude запросил запрещённые инструменты: " + ", ".join(names)
        named = {"error_max_turns": "Claude исчерпал лимит шагов.",
                 "error_max_budget": "Claude исчерпал бюджет запуска.",
                 "error_during_execution": "Claude прервал выполнение."}
        subtype = (result or {}).get("subtype")
        if subtype in named:
            return named[subtype]
        return clean(state.get("stderr", "").strip())

    async def run(self, prompt, workspace, directory, emit, cancel_event,
                  readonly=False, schema=None):
        directory.mkdir(parents=True, exist_ok=True)
        argv = [claude_binary(), "-p", "--output-format", "stream-json", "--verbose",
                # Ignores the user's own settings.json, which may allow Bash and
                # bypassPermissions, and confines file tools to the working roots.
                "--restricted",
                # dontAsk denies anything that would need approval, and Write
                # needs it - measured: a writing turn produced two Write denials
                # and no files. acceptEdits approves edits without a prompt, and
                # --restricted still confines them to the workspace (measured
                # too: a write to /tmp was refused by the provider itself).
                "--permission-mode", "dontAsk" if readonly else "acceptEdits",
                "--permission-prompts", "none",
                "--disallowedTools", "mcp__*", "--strict-mcp-config",
                "--disable-slash-commands", "--no-session-persistence",
                "--max-turns", "20" if readonly else "60",
                "--tools", self.TOOLS_READONLY if readonly else self.TOOLS_WRITE]
        if schema:
            schema_path = directory / "schema.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            argv += ["--json-schema", json.dumps(schema),
                     "--append-system-prompt",
                     "Return exactly one JSON object matching the supplied schema. "
                     "No prose, no Markdown fences."]
        (directory / "prompt.txt").write_text(clean(prompt), encoding="utf-8")
        state = {"result": None, "text": "", "stderr": "", "calls": {}}
        raw_log = directory / "events.jsonl"

        def call_id(identifier):
            # The turn/attempt prefix keeps cards from separate attempts apart.
            return "%s:%s:%s" % (directory.parent.name, directory.name, identifier)

        def line(stream, text):
            if stream != "stdout":
                return
            try:
                event = json.loads(text)
            except ValueError:
                raise RuntimeFailure("Claude вернул повреждённый JSON-поток.") from None
            with raw_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(clean(event), ensure_ascii=False) + "\n")
            kind = event.get("type")
            if kind == "result":
                state["result"] = event
                return
            if kind not in ("assistant", "user"):
                # system/init, task summaries, rate-limit notices and whatever a
                # later version adds: recorded, not fatal. Only an unparsable
                # line means the stream itself is broken.
                return
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict):
                    self._handle(block, call_id, emit, state)

        result = await process(argv, cwd=workspace, input_text=prompt,
                               environment=worker_environment(), cancel_event=cancel_event,
                               timeout=480, on_line=line)
        state["stderr"] = result["stderr"]
        (directory / "stderr.txt").write_text(clean(result["stderr"]), encoding="utf-8")
        final = state["result"]
        if final is None or final.get("is_error") or result["exit_code"]:
            reason = self._failure(state, final)
            raise RuntimeFailure("Claude не завершил ход. " + (
                reason if reason else "Подробности: %s" % (directory / "stderr.txt")))
        structured = final.get("structured_output")
        if schema and structured is not None:
            text = json.dumps(structured, ensure_ascii=False)
        else:
            text = clean(final.get("result") or state["text"])
        (directory / "final.txt").write_text(text, encoding="utf-8")
        if not text.strip():
            raise RuntimeFailure("Claude завершился без ответа.")
        return {"text": text, "usage": self._usage(final.get("usage")), "completed": True}

    def _handle(self, block, call_id, emit, state):
        kind = block.get("type")
        if kind == "text":
            text = block.get("text") or ""
            if text.strip():
                state["text"] = clean(text)
                emit("message", role="assistant", text=state["text"])
        elif kind == "tool_use":
            name = block.get("name") or "unknown"
            identifier = block.get("id") or name
            arguments = block.get("input") if isinstance(block.get("input"), dict) else {}
            if name == "TodoWrite":
                emit("plan", steps=[{"id": str(index + 1), "title": item.get("content", ""),
                                     "completed": item.get("status") == "completed"}
                                    for index, item in enumerate(arguments.get("todos") or [])
                                    if isinstance(item, dict)])
                return
            command = self._command(name, arguments)
            state["calls"][identifier] = {"kind": self.KINDS.get(name, "mcp_tool_call"),
                                          "command": command}
            files = ([{"path": arguments["file_path"]}]
                     if isinstance(arguments.get("file_path"), str) else [])
            emit("tool", kind=state["calls"][identifier]["kind"], command=command,
                 status="running", output="", exit_code=None, files=files,
                 item_id=identifier, call_id=call_id(identifier), lifecycle="started")
        elif kind == "tool_result":
            identifier = block.get("tool_use_id") or ""
            started = state["calls"].get(identifier)
            if not started:
                return  # A result without its call would open a card that never closes.
            failed = bool(block.get("is_error"))
            emit("tool", kind=started["kind"], command=started["command"],
                 status="failed" if failed else "completed",
                 output=clean(self._text_of(block.get("content")))[-6000:],
                 exit_code=1 if failed else 0, item_id=identifier,
                 call_id=call_id(identifier), lifecycle="completed")


class JevJudge:
    """One decision: cache lookup, then the bounded HTTP exchange in a child."""

    async def _wait(self, seconds, cancel_event):
        """Back off without going deaf to a stop request."""
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return
        raise asyncio.CancelledError()

    async def ask(self, state, questions, directory, emit, cancel_event):
        directory.mkdir(parents=True, exist_ok=True)
        request = {"model": "jev-1.13.0", "state": clean(state), "questions": questions}
        transport.check_size(request)  # Refuse an impossible request before spawning anything.
        key = transport.request_key(request)
        path = directory / "request.json"
        path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        response_path = directory / "response.json"
        cached = transport.read_cache(key)
        if cached is not None:
            # A hit costs a file read, not a process: the saved answer is the
            # answer to this exact state and question set.
            response_path.write_text(json.dumps(cached, ensure_ascii=False, indent=2), encoding="utf-8")
            return dict(cached, _cached=True, _elapsed_ms=0.0)
        blocked = transport.breaker_block()
        if blocked:
            raise RuntimeFailure(blocked)
        helper = Path(__file__).with_name("judge_call.py")
        attempts = len(transport.RETRY_DELAYS) + 1
        reason = "Jev API недоступен."
        for attempt in range(attempts):
            result = await process([sys.executable, helper, path, response_path],
                                   cwd=directory, cancel_event=cancel_event, timeout=25,
                                   environment=dict(os.environ))
            if not result["exit_code"]:
                response = json.loads(response_path.read_text(encoding="utf-8"))
                transport.write_cache(key, response)  # Store the provider's answer, not our timing.
                transport.record_success()
                response["_elapsed_ms"] = result["elapsed_ms"]
                return response
            # The child reports the lab client's own message; that text is the
            # only place the HTTP status survives the process boundary.
            reason = clean(result["stderr"].strip()) or reason
            if attempt + 1 == attempts or not transport.retryable(reason):
                break
            emit("message", role="policy",
                 text="Jev: %s Повтор %s из %s." % (reason, attempt + 1, attempts - 1))
            await self._wait(transport.RETRY_DELAYS[attempt], cancel_event)
        transport.record_failure()
        raise RuntimeFailure(reason)
