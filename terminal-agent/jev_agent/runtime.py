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
