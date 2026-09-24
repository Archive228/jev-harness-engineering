"""What surrounds a Jev call: a cache, a size guard, retries and a breaker.

The call itself stays in a child process, because the lab client bounds the
whole HTTP exchange with SIGALRM and that only works in a main thread. Nothing
here opens a socket. The cache is read before the child is spawned, so a hit
costs a file read instead of a process; the breaker is a file rather than a
module variable, because every call is a new process and in-memory state would
not survive between them.

A cached answer is returned with ``_cached`` set, so the caller can keep
metering honest instead of billing the same tokens twice.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

# Refuse oversized requests here rather than learning about them from a 400.
MAX_REQUEST_BYTES = 90_000
CACHE_TTL_SECONDS = 24 * 3600
# Consecutive failures that open the breaker, and how long it stays open. After
# the cooldown one probe is allowed through: a success closes it, a failure
# re-opens it for longer.
BREAKER_FAILURES = 3
BREAKER_COOLDOWN_SECONDS = 30
MAX_COOLDOWN_SECONDS = 300
RETRY_DELAYS = (0.5, 1.5)  # Two retries; attempt count is len(RETRY_DELAYS) + 1.

# Transport faults worth another attempt. A malformed body is not one of them:
# the provider already answered, and asking again costs tokens for the same bug.
RETRYABLE_MARKERS = ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504", "HTTP 529",
                     "URLError", "TimeoutError", "OSError", "ConnectionError", "socket.timeout")


class TransportRefusal(RuntimeError):
    """Refused before any network call was attempted."""


def enabled():
    return os.environ.get("JEV_CACHE", "on").lower() not in ("off", "0", "false")


def root():
    configured = os.environ.get("JEV_CACHE_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".jev"


def _prepare(path):
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)  # The cache holds request state, including file excerpts.
    except OSError:
        pass
    return path


def request_key(request):
    """A stable identity for one question set asked about one state."""
    payload = json.dumps({"model": request.get("model"), "state": request.get("state"),
                          "questions": request.get("questions")},
                         ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_size(request):
    """Raise before spawning anything when the state cannot fit one request."""
    size = len(json.dumps(request, ensure_ascii=False, default=str).encode("utf-8"))
    if size > MAX_REQUEST_BYTES:
        raise TransportRefusal(
            "Jev request too large: %s of %s bytes. Shorten the state." % (size, MAX_REQUEST_BYTES))
    return size


def read_cache(key, now=None):
    """A previously saved answer, or None. A damaged entry is a miss, not an error."""
    if not enabled():
        return None
    path = root() / "cache" / (key + ".json")
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    now = time.time() if now is None else now
    saved = entry.get("saved_at")
    if not isinstance(saved, (int, float)) or now - saved > CACHE_TTL_SECONDS:
        return None
    response = entry.get("response")
    return response if isinstance(response, dict) else None


def write_cache(key, response, now=None):
    """Store atomically; a failure to cache must never fail the call."""
    if not enabled() or not isinstance(response, dict):
        return False
    try:
        directory = _prepare(root() / "cache")
        temporary = directory / (key + "." + uuid.uuid4().hex + ".tmp")
        temporary.write_text(json.dumps({"saved_at": time.time() if now is None else now,
                                         "response": response},
                                        ensure_ascii=False), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(directory / (key + ".json"))
        return True
    except OSError:
        return False


def _breaker_path():
    return root() / "breaker.json"


def _read_breaker():
    try:
        state = json.loads(_breaker_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"failures": 0, "open_until": 0.0}
    failures = state.get("failures")
    until = state.get("open_until")
    return {"failures": failures if isinstance(failures, int) and failures >= 0 else 0,
            "open_until": float(until) if isinstance(until, (int, float)) else 0.0}


def _write_breaker(state):
    try:
        directory = _prepare(root())
        temporary = directory / ("breaker." + uuid.uuid4().hex + ".tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(_breaker_path())
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EROFS, errno.ENOSPC):
            raise


def breaker_block(now=None):
    """The reason this call must not be attempted, or None."""
    state = _read_breaker()
    remaining = state["open_until"] - (time.time() if now is None else now)
    if remaining > 0:
        return ("Jev unavailable after %s failures in a row; retry in %ss."
                % (state["failures"], int(remaining) + 1))
    return None


def record_success():
    if _read_breaker()["failures"]:
        _write_breaker({"failures": 0, "open_until": 0.0})


def record_failure(now=None):
    """Count one failure and open the breaker once they accumulate."""
    state = _read_breaker()
    failures = state["failures"] + 1
    open_until = 0.0
    if failures >= BREAKER_FAILURES:
        # Each further failure past the threshold waits longer, up to a ceiling.
        cooldown = min(MAX_COOLDOWN_SECONDS,
                       BREAKER_COOLDOWN_SECONDS * (2 ** (failures - BREAKER_FAILURES)))
        open_until = (time.time() if now is None else now) + cooldown
    _write_breaker({"failures": failures, "open_until": open_until})
    return open_until


def retryable(message):
    """True when another attempt could plausibly succeed."""
    return any(marker in (message or "") for marker in RETRYABLE_MARKERS)
