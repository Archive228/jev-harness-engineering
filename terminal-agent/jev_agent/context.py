"""Bounded, attributed source evidence. Retrieval is a shortlist, not a code audit."""
import difflib
import fnmatch
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import time

from .runtime import clean


MAX_FILE_BYTES = 64 * 1024
MAX_READ_BYTES = 4 * 1024 * 1024
MAX_FILES = 512
MAX_ENTRIES = 4096
MAX_CANDIDATES = 5
MAX_EXCERPT_BYTES = 1600
EXCLUDED_DIRS = {"node_modules", "vendor", "dist", "build", "coverage", "__pycache__", "target"}
TEXT_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".h",
                 ".cpp", ".hpp", ".rb", ".php", ".sh", ".md", ".txt", ".toml", ".yaml",
                 ".yml", ".json", ".sql", ".css", ".html", ".vue", ".svelte"}
SECRET_NAME = re.compile(r"(?:credential|secret|password|private[-_]?key|^auth(?:\.|$)|^id_[re]sa)", re.I)
SECRET_CONTENT = re.compile(
    r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)|(?:apikey_[A-Za-z0-9_]+|new1_[a-fA-F0-9]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})|"
    r"(?im:^[ \t]*[\"']?(?:[\w-]*api[_-]?key|access[_-]?token|password|client[_-]?secret)[\"']?\s*[:=])")
# Filler words dropped before matching a request against the project. Not interface
# text: it is never displayed. The Russian half is here because the person writing the
# request may write in Russian even though the interface is English.
STOP_WORDS = set("the and for this that from with into code file files please create change make show explain "
                 "это как для что или мне надо нужно файл файлы сделай создай покажи объясни".split())


def tokens(text):
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return {part for part in re.findall(r"[^\W_]+", text.lower(), re.UNICODE)
            if len(part) > 1 and not part.isdigit() and part not in STOP_WORDS}


def safe_name(relative):
    path = Path(relative)
    return (not path.is_absolute() and ".." not in path.parts and
            all(not p.startswith(".") and p not in EXCLUDED_DIRS and not SECRET_NAME.search(p)
                for p in path.parts) and path.suffix.lower() in TEXT_SUFFIXES and
            path.name not in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"} and
            not path.name.endswith((".env", ".key", ".pem")))


def read_safe_text(root, relative, max_bytes=MAX_FILE_BYTES, accounting=None):
    """Open each path component without following symlinks, including directory swaps."""
    if not safe_name(relative):
        return None
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
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            return None
        raw = b""
        while len(raw) <= max_bytes:
            block = os.read(descriptor, min(16384, max_bytes + 1 - len(raw)))
            if not block:
                break
            raw += block
            if accounting is not None:
                accounting["bytes"] += len(block)
        if len(raw) > max_bytes or b"\0" in raw:
            return None
        text = raw.decode("utf-8")
        if SECRET_CONTENT.search(text):
            return None
        return {"text": clean(text), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    except (OSError, UnicodeError, ValueError):
        return None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _local_ignored(root, relative):
    """Conservative .gitignore fallback outside Git; negations never reinclude secrets."""
    path = Path(relative)
    for level in range(len(path.parts)):
        base = root.joinpath(*path.parts[:level])
        ignore = base / ".gitignore"
        if not ignore.is_file() or ignore.is_symlink() or ignore.stat().st_size > 16384:
            continue
        subpath = "/".join(path.parts[level:])
        for line in ignore.read_text(encoding="utf-8", errors="replace").splitlines():
            pattern = line.strip()
            if not pattern or pattern.startswith(("#", "!")):
                continue
            pattern = pattern.lstrip("/").rstrip("/")
            prefixes = ["/".join(path.parts[level:i + 1]) for i in range(level, len(path.parts))]
            if (fnmatch.fnmatchcase(subpath, pattern) or any(fnmatch.fnmatchcase(p, pattern) for p in prefixes)
                    or ("/" not in pattern and any(fnmatch.fnmatchcase(p, pattern) for p in path.parts[level:]))):
                return True
    return False


def ignored_paths(root, paths):
    root = Path(root).resolve()
    ignored = {p for p in paths if _local_ignored(root, p)}
    try:
        repository = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    timeout=2, check=False)
        # The selected workspace is the evidence boundary. A containing repo may
        # ignore the whole session directory merely to keep generated work out of
        # Git; that must not suppress every source file in its workspace. Nested
        # workspaces use only their own conservative .gitignore rules above.
        if repository.returncode or Path(repository.stdout.decode("utf-8", "replace").strip()).resolve() != root:
            return ignored
        result = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "-z", "--stdin"],
                                input="\0".join(paths).encode() + b"\0", stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=2, check=False)
        if result.returncode in (0, 1):
            ignored.update(p for p in result.stdout.decode("utf-8", "replace").split("\0") if p)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ignored


def shortlist(root, query, *, max_files=MAX_FILES, max_read_bytes=MAX_READ_BYTES):
    root = Path(root).resolve()
    started = time.monotonic()
    limit = min(MAX_FILES, max(1, max_files))
    byte_limit = min(MAX_READ_BYTES, max(0, max_read_bytes))
    paths, pending, entries, partial = [], [root], 0, False
    while pending and len(paths) < limit and entries < MAX_ENTRIES:
        directory = pending.pop()
        try:
            with os.scandir(directory) as scan:
                for entry in scan:
                    entries += 1
                    if entries >= MAX_ENTRIES or time.monotonic() - started > 2:
                        partial = True
                        break
                    if entry.is_symlink() or entry.name.startswith(".") or SECRET_NAME.search(entry.name):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in EXCLUDED_DIRS:
                            pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        relative = Path(entry.path).relative_to(root).as_posix()
                        if safe_name(relative):
                            paths.append(relative)
                            if len(paths) >= limit:
                                partial = True
                                break
        except OSError:
            partial = True
        if time.monotonic() - started > 2:
            break
    partial = partial or bool(pending)
    paths.sort()
    ignored = ignored_paths(root, paths) if paths else set()
    query_terms = tokens(query[:5000])
    candidates, scanned = [], 0
    accounting = {"bytes": 0}
    for relative in paths:
        if relative in ignored:
            continue
        remaining = byte_limit - accounting["bytes"]
        if remaining <= 0 or time.monotonic() - started > 4:
            partial = True
            break
        # Reserve one byte for a concurrent file-growth probe inside the total read bound.
        source = read_safe_text(root, relative, min(MAX_FILE_BYTES, max(0, remaining - 1)), accounting)
        scanned += 1
        if source is None:
            partial = True
            continue
        lines = source["text"].splitlines()
        path_score = 3 * len(tokens(relative) & query_terms)
        line_scores = [len(tokens(line) & query_terms) for line in lines]
        peak = max(line_scores or [0])
        if not path_score and not peak:
            continue
        at = line_scores.index(peak) if peak else 0
        start = max(0, at - 3)
        included = []
        used = 0
        clipped = False
        for line in lines[start:start + 9]:
            encoded = (line + "\n").encode("utf-8")
            available = MAX_EXCERPT_BYTES - used
            if len(encoded) > available:
                included.append(encoded[:available].decode("utf-8", "ignore"))
                clipped = True
                break
            included.append(line + "\n")
            used += len(encoded)
        candidates.append({"path": relative, "start_line": start + 1,
                           "end_line": start + len(included), "sha256": source["sha256"],
                           "excerpt": "".join(included), "excerpt_truncated": clipped,
                           "lexical_score": path_score + peak + len(tokens(source["text"]) & query_terms)})
    candidates.sort(key=lambda item: (-item["lexical_score"], item["path"]))
    partial = partial or len(candidates) > MAX_CANDIDATES
    candidates = candidates[:MAX_CANDIDATES]
    for index, candidate in enumerate(candidates):
        candidate["id"] = "c%s" % index
    return {"candidates": candidates, "partial": partial, "files_scanned": scanned,
            "bytes_read": accounting["bytes"], "entries_seen": entries, "ignored_files": len(ignored),
            "no_matches": not bool(candidates)}


def capture_texts(root, paths, preferred=()):
    """At most ten safe files / 256 KiB. Missing previous text stays unavailable."""
    captured = {}
    accounting = {"bytes": 0}
    order = [path for path in dict.fromkeys(list(preferred) + sorted(paths)) if safe_name(path)][:MAX_FILES]
    ignored = ignored_paths(Path(root), order) if order else set()
    for path in order:
        if len(captured) >= 10 or accounting["bytes"] >= 256 * 1024:
            break
        if path in ignored:
            continue
        source = read_safe_text(root, path, min(MAX_FILE_BYTES, max(0, 256 * 1024 - accounting["bytes"] - 1)), accounting)
        if source:
            captured[path] = source
    return captured


def diff_details(root, changed, before_snapshot, after_snapshot, captured):
    details, total = {}, 0
    accounting = {"bytes": 0}
    ignored = ignored_paths(Path(root), changed[:10]) if changed else set()
    for path in changed[:10]:
        if not safe_name(path) or path in ignored:
            continue
        status = "added" if path not in before_snapshot["files"] else "deleted" if path not in after_snapshot["files"] else "modified"
        before = captured.get(path)
        after = read_safe_text(root, path, min(MAX_FILE_BYTES, max(0, 256 * 1024 - accounting["bytes"] - 1)),
                               accounting) if status != "deleted" else None
        hashes = {"before_sha256": before_snapshot["files"].get(path), "after_sha256": after_snapshot["files"].get(path)}
        if ((status != "added" and (not before or before["sha256"] != before_snapshot["files"][path])) or
                (status != "deleted" and (not after or after["sha256"] != after_snapshot["files"][path]))):
            details[path] = {"status": status, "diff": "", "truncated": True,
                             "reason": "Safe text unavailable within capture bounds; no diff reconstructed.", **hashes}
            continue
        lines = difflib.unified_diff(before["text"].splitlines(keepends=True) if before else [],
                                     after["text"].splitlines(keepends=True) if after else [],
                                     fromfile="a/" + path if before else "/dev/null",
                                     tofile="b/" + path if after else "/dev/null")
        raw = "".join(lines).encode("utf-8")
        budget = min(64 * 1024, 256 * 1024 - total)
        text = raw[:budget].decode("utf-8", "ignore")
        details[path] = {"status": status, "diff": text, "truncated": len(raw) > budget, **hashes}
        total += len(text.encode("utf-8"))
    return details
