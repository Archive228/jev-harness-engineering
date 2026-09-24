"""Local session navigation, drafts and inspectable artifacts for the terminal.

Independently implemented from the interaction patterns documented in
research/upstream-audit.md. Nothing here calls a model or executes file content.
"""
import json
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile

from .runtime import clean


MAX_TEXT_BYTES = 65536
MAX_DRAFT_CHARS = 20000
EXCLUDED = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
            ".sessions", ".ssh", ".aws", ".codex", "dist", "build"}


def _directory(session):
    return Path(getattr(session, "directory", session))


def _atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".write-", delete=False) as handle:
        tmp = Path(handle.name)
        try:
            os.chmod(tmp, 0o600)
            handle.write(text)
            handle.flush()
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def _json_file(path, max_bytes=4_000_000):
    if path.is_symlink() or path.stat().st_size > max_bytes:
        raise ValueError("State file is too large or is a symlink")
    return json.loads(path.read_text(encoding="utf-8"))


def list_sessions(base):
    """Recent sessions by last activity; malformed/interrupted entries are skipped."""
    base = Path(base)
    if not base.is_dir():
        return []
    result = []
    for directory in base.iterdir():
        if directory.is_symlink() or not directory.is_dir():
            continue
        path = directory / "session.json"
        try:
            metadata = _json_file(path)
            history = metadata.get("history", [])
            if not isinstance(history, list):
                continue
            prompts = [entry.get("text", "") for entry in history
                       if isinstance(entry, dict) and entry.get("role") == "user"]
            title = metadata.get("title") or (prompts[0] if prompts else "New session")
            latest = sorted(directory.glob("turn-*/result.json"))
            status = "idle"
            if latest:
                try:
                    status = _json_file(latest[-1]).get("status", "unknown")
                except (OSError, ValueError, AttributeError):
                    status = "unknown"
            result.append({"id": str(metadata["id"]), "directory": str(directory.resolve()),
                           "title": " ".join(str(clean(title)).split())[:140],
                           "workspace": str(metadata.get("workspace", "")),
                           "updated_at": path.stat().st_mtime, "turns": len(prompts),
                           "status": status,
                           "execution_mode": metadata.get("execution_mode", "auto"),
                           "jev_mode": metadata.get("jev_mode", "assist")})
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            continue
    return sorted(result, key=lambda row: row["updated_at"], reverse=True)


def save_draft(session, text):
    if not isinstance(text, str) or len(text) > MAX_DRAFT_CHARS:
        raise ValueError("Draft is limited to 20,000 characters")
    _atomic_text(_directory(session) / "draft.txt", text)


def load_draft(session):
    path = _directory(session) / "draft.txt"
    try:
        if path.is_symlink() or path.stat().st_size > MAX_DRAFT_CHARS * 4:
            return ""
        text = path.read_text(encoding="utf-8")
        return text if len(text) <= MAX_DRAFT_CHARS else ""
    except (OSError, UnicodeError):
        return ""


def _artifact_path(session, relative_path):
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or any(p in {".", ".."} for p in relative.parts):
        raise ValueError("A relative path inside the workspace is required")
    lower_parts = [p.lower() for p in relative.parts]
    name = relative.name.lower()
    if (any(p in EXCLUDED for p in lower_parts) or name.startswith(".env")
            or name.endswith((".key", ".pem", ".p12", ".pfx"))
            or "credential" in name or name in {"auth.json", "id_rsa", "id_ed25519", "secrets.json"}):
        raise ValueError("Key files and service directories are not shown")
    root = Path(session.workspace).resolve()
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlinks are not opened")
    try:
        path.resolve().relative_to(root)
    except ValueError:
        raise ValueError("Path leads outside the workspace") from None
    return path


def _captured_diffs(session):
    """Latest captured diff per file; these are evidence, not reconstructed history."""
    result = {}
    for path in sorted(_directory(session).glob("turn-*/attempt-*-diffs.json"), reverse=True):
        try:
            data = _json_file(path, 2_000_000)
            if not isinstance(data, dict):
                continue
            for name, entry in data.items():
                if isinstance(entry, dict):
                    result.setdefault(name, entry)
        except (OSError, ValueError):
            continue
    return result


def _read_workspace_file(root, relative):
    """Bounded descriptor read, refusing symlink swaps at every path component."""
    descriptors = []
    try:
        descriptor = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        parts = Path(relative).parts
        for part in parts[:-1]:
            descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            descriptors.append(descriptor)
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        descriptors.append(descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("Preview is available for regular files only")
        chunks = []
        remaining = MAX_TEXT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(16384, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def list_artifacts(session):
    changes = {}
    for event in session.events():
        if event.get("type") == "files":
            for path in event.get("data", {}).get("changed", []):
                if isinstance(path, str):
                    changes[path] = "modified"
    for name, entry in _captured_diffs(session).items():
        changes[name] = entry.get("status", "modified")
    result = []
    for name, status in changes.items():
        if len(result) >= 300:
            break
        try:
            path = _artifact_path(session, name)
            result.append({"path": name, "status": status if path.exists() else "deleted"})
        except (ValueError, OSError):
            continue
    # Also make existing project files accessible before the first edit.
    known = {item["path"] for item in result}
    for folder, dirs, names in os.walk(session.workspace, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED
                         and not Path(folder, d).is_symlink())
        for name in sorted(names):
            if len(result) >= 300:
                return result
            relative = Path(folder, name).relative_to(session.workspace).as_posix()
            if relative in known:
                continue
            try:
                _artifact_path(session, relative)
                result.append({"path": relative, "status": "existing"})
            except (ValueError, OSError):
                continue
    return result


def read_artifact(session, relative_path):
    path = _artifact_path(session, relative_path)
    captured = _captured_diffs(session).get(relative_path, {})
    result = {"path": relative_path, "text": "", "diff": clean(captured.get("diff", "")),
              "notice": "", "truncated": bool(captured.get("truncated", False)),
              "language": {".py": "python", ".js": "javascript", ".ts": "typescript",
                           ".json": "json", ".md": "markdown", ".sh": "bash",
                           ".html": "html", ".css": "css"}.get(path.suffix.lower(), "text")}
    try:
        data = _read_workspace_file(Path(session.workspace).resolve(), relative_path)
    except (OSError, ValueError):
        result["notice"] = "File deleted or unavailable."
        return result
    if b"\x00" in data:
        result["notice"] = "Binary file: no text preview available."
        return result
    try:
        # Decode the whole bounded read first so a split final code point does not
        # hide an otherwise valid UTF-8 file.
        import codecs
        decoder = codecs.getincrementaldecoder("utf-8")()
        result["text"] = clean(decoder.decode(data[:MAX_TEXT_BYTES], final=len(data) <= MAX_TEXT_BYTES))
    except UnicodeError:
        result["notice"] = "Not UTF-8 text: no preview available."
        return result
    result["truncated"] = result["truncated"] or len(data) > MAX_TEXT_BYTES
    if not captured:
        result["notice"] = "Showing the current file. No diff was saved for this change."
    else:
        result["notice"] = "Diff of the last saved attempt; the file text is shown as it is now."
        if (len(data) <= MAX_TEXT_BYTES and captured.get("after_sha256")
                and hashlib.sha256(data).hexdigest() != captured["after_sha256"]):
            result["notice"] += " The file changed after that diff was saved."
    if len(data) > MAX_TEXT_BYTES:
        result["notice"] += " Preview limited to 64 KiB."
    return result


def _fenced(text, language="text"):
    text = str(clean(text))
    fence = "`" * max(3, max((len(part) for part in re.findall(r"`+", text)), default=0) + 1)
    return fence + language + "\n" + text + "\n" + fence


def export_session(session):
    """Export the conversation plus typed decisions and actual tools as Markdown."""
    lines = ["# JEVIS session " + str(session.id),
             "", "Workspace: " + str(session.workspace),
             "", "## Conversation", ""]
    for entry in session.history:
        role = "User" if entry.get("role") == "user" else "Worker / harness reply"
        lines.extend(["### " + role, "", _fenced(entry.get("text", "")), ""])
    lines.extend(["## Observed events", ""])
    for event in session.events():
        if event.get("type") not in {"jev", "tool", "checks", "context", "triage", "brief", "end", "error"}:
            continue
        lines.extend(["### #{} · {}".format(event.get("seq", "?"), event["type"]), "",
                      _fenced(json.dumps(clean(event.get("data", {})), ensure_ascii=False, indent=2), "json"), ""])
    brief = _directory(session) / "brief.json"
    if brief.is_file():
        data = _json_file(brief, 1_000_000)
        lines.extend(["## Task clarification and agreed plan", "",
                      _fenced(json.dumps(clean(data), ensure_ascii=False, indent=2), "json"), ""])
    path = _directory(session) / "exports" / "session.md"
    _atomic_text(path, "\n".join(lines))
    return path
