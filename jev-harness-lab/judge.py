"""TypeSafe REST client; demo outputs are explicitly synthetic fixtures."""
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
import signal


@contextmanager
def wall_deadline(seconds):
    """The CLI is single-threaded and targets POSIX; bound the whole HTTP exchange."""
    def expired(_signum, _frame):
        raise TimeoutError("API wall-clock deadline reached")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, max(0.001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1])

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
TICKET = "В Safari экспорт PDF завершается ошибкой. В Chrome тот же документ экспортируется. Сейчас пользуюсь Chrome, но хочу вернуть экспорт в Safari."
TICKET_QUESTIONS = {
    "category": {"type": "choice", "instructions": "What category best describes the reported problem?",
                 "criteria": {"export": "Exporting or downloading a document", "account": "Signing in or account access", "payment": "Billing or payment", "other": "None of these categories"}},
    "impact": {"type": "score", "instructions": "How much does the issue obstruct the user's task?",
               "criteria": ["Cosmetic issue; functionality works", "Function is broken, but a working workaround exists", "Task is blocked and no working workaround is stated"]},
    "has_workaround": {"type": "noul", "instructions": "Does the message explicitly state a working workaround?"},
}


class JudgeError(RuntimeError):
    pass


def probability(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and 0 <= value <= 1)


def response_usage(response):
    """Return complete, validated provider counters; missing is never zero."""
    usage = response.get("usage") if isinstance(response, dict) else None
    if (not isinstance(usage, dict)
            or any(not isinstance(usage.get(name), int)
                   or isinstance(usage.get(name), bool) or usage[name] < 0
                   for name in ("input_tokens", "output_tokens"))):
        raise JudgeError("Missing or invalid usage counters")
    return {name: usage[name] for name in ("input_tokens", "output_tokens")}


def validate_response(response, questions):
    answers = response.get("answers") if isinstance(response, dict) else None
    if not isinstance(answers, dict):
        raise JudgeError("Response has no answers object")
    if not isinstance(response.get("model"), str) or not response["model"].strip():
        raise JudgeError("Missing or invalid response model")
    response_usage(response)
    for key, question in questions.items():
        answer = answers.get(key)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise JudgeError("Missing answer or wrong type for " + key)
        if question["type"] == "noul":
            if not probability(answer.get("noul")):
                raise JudgeError("Invalid Noul value")
            continue
        expected = set(question["criteria"]) if question["type"] == "choice" else set(str(i) for i in range(len(question["criteria"])))
        distribution = answer.get("probabilities")
        if (not isinstance(distribution, dict) or set(distribution) != expected
                or not all(probability(v) for v in distribution.values())
                or abs(sum(distribution.values()) - 1) > 0.02
                or not probability(answer.get("confidence"))):
            raise JudgeError("Invalid distribution/confidence for " + key)
        if question["type"] == "choice" and (not isinstance(answer.get("choice"), str)
                                             or answer["choice"] not in expected):
            raise JudgeError("Choice outside registered options")
        if question["type"] == "choice" and distribution[answer["choice"]] + 1e-6 < max(distribution.values()):
            raise JudgeError("Choice is not a maximum-probability option")
        if question["type"] == "score":
            score = answer.get("score")
            if (not isinstance(score, (int, float)) or isinstance(score, bool)
                    or not math.isfinite(score) or not 0 <= score <= len(expected) - 1):
                raise JudgeError("Invalid Score value")
            legend = answer.get("legend")
            if not isinstance(legend, dict) or set(legend) != expected:
                raise JudgeError("Missing or invalid Score legend")
            mean = sum(int(k) * v for k, v in distribution.items())
            if abs(mean - score) > 0.03:
                raise JudgeError("Score disagrees with its probability-weighted position")
    return response


def demo_response(questions):
    answers = {}
    for key, question in questions.items():
        if question["type"] == "noul":
            answers[key] = {"type": "noul", "noul": 0.99}
        elif question["type"] == "score":
            answers[key] = {"type": "score", "score": 1.0, "confidence": 1.0,
                            "legend": {str(i): v for i, v in enumerate(question["criteria"])},
                            "probabilities": {str(i): float(i == 1) for i in range(len(question["criteria"]))}}
        else:
            selected = "export" if "export" in question["criteria"] else "D2"
            if selected not in question["criteria"]:
                selected = "none_suitable"
            answers[key] = {"type": "choice", "choice": selected, "confidence": 1.0,
                            "probabilities": {k: float(k == selected) for k in question["criteria"]}}
    return {"model": "SYNTHETIC-DEMO-NOT-JEV", "answers": answers,
            "usage": {"input_tokens": 0, "output_tokens": 0}}


class Judge:
    def __init__(self, mode, directory, timeout=20, model=MODEL):
        self.mode, self.directory, self.timeout, self.model = mode, Path(directory), timeout, model
        self.calls = 0
        self.remote_requests = 0
        self.total_ms = 0.0
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.usage_complete = True
        self.usage_reported_requests = 0

    def ask(self, state, questions):
        self.calls += 1
        request = {"state": state, "model": self.model, "questions": questions}
        record = {"mode": self.mode, "synthetic": self.mode == "demo", "request": request}
        remote_attempted = False
        start = time.monotonic()
        try:
            if self.mode == "demo":
                response = demo_response(questions)
            else:
                key = os.environ.get("TYPESAFE_API_KEY")
                if not key:
                    raise JudgeError("TYPESAFE_API_KEY is required for --mode live")
                call = urllib.request.Request(ENDPOINT, data=json.dumps(request).encode(), method="POST",
                                              headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                self.remote_requests += 1
                remote_attempted = True
                with wall_deadline(self.timeout):
                    with urllib.request.urlopen(call, timeout=self.timeout) as result:
                        raw = result.read(2_000_001)
                        if len(raw) > 2_000_000:
                            raise JudgeError("API response too large")
                        response = json.loads(raw)
            record["response"] = response  # Preserve provider JSON, including extra fields.
            usage = response_usage(response)
            # A billed response still consumes tokens when its answers are invalid.
            for name in self.usage:
                self.usage[name] += usage[name]
            record["usage_reported"] = True
            if remote_attempted:
                self.usage_reported_requests += 1
            validate_response(response, questions)
            return response
        except urllib.error.HTTPError as exc:
            record["error"] = "HTTP %s" % exc.code
            # Never persist a response's entire headers or Authorization data.
            for name in ("x-request-id", "request-id"):
                value = exc.headers.get(name) if exc.headers else None
                if value and len(value) <= 200 and all(c.isalnum() or c in "-_.:" for c in value):
                    record["provider_request_id"] = value
                    break
            raise JudgeError(record["error"]) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            record["error"] = "API transport/JSON failure: " + type(exc).__name__
            raise JudgeError(record["error"]) from None
        except JudgeError as exc:
            record["error"] = str(exc)
            raise
        finally:
            record.setdefault("usage_reported", False)
            if remote_attempted and (record.get("error") or not record["usage_reported"]):
                self.usage_complete = False
            record["usage_complete"] = not remote_attempted or (record["usage_reported"] and not record.get("error"))
            record["elapsed_ms"] = round((time.monotonic() - start) * 1000, 2)
            self.total_ms += record["elapsed_ms"]
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / ("judge-%03d.json" % self.calls)).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
