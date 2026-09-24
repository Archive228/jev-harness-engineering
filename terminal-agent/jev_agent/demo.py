"""A judge and a worker that answer from the schema they were asked with.

The point is not a canned transcript. The real executor, the real retrieval,
the real checks and the real stopping rules run; only the two network-bound
edges are replaced. Answers are derived from the request, so a demo turn is
reproducible, and every synthetic answer is labelled at the source: the judge
reports the model name the lab already reserves for this, and its responses
carry ``synthetic``, so a demo run can never be mistaken for a measurement.
"""
import hashlib
import json

SYNTHETIC_MODEL = "SYNTHETIC-DEMO-NOT-JEV"

# Which option a demo prefers when a question offers several. Everything else
# falls back to the first registered criterion, never to chance.
PREFERRED = {"route": "implement", "next_action": "finish", "category": "code"}

DEMO_TOOL = '''"""Small utility created by the JEVIS demo worker."""


def summarise(values):
    """Return count, total and mean of a sequence of numbers."""
    values = [float(v) for v in values]
    if not values:
        return {"count": 0, "total": 0.0, "mean": 0.0}
    total = sum(values)
    return {"count": len(values), "total": total, "mean": total / len(values)}
'''

DEMO_TEST = '''import unittest

from demo_tool import summarise


class SummariseTests(unittest.TestCase):
    def test_empty_sequence_has_no_mean(self):
        self.assertEqual(summarise([]), {"count": 0, "total": 0.0, "mean": 0.0})

    def test_mean_is_the_total_over_the_count(self):
        self.assertEqual(summarise([1, 2, 3]), {"count": 3, "total": 6.0, "mean": 2.0})


if __name__ == "__main__":
    unittest.main()
'''


def _digest(*parts):
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).digest()


def _unit(*parts):
    """A reproducible value in [0, 1) derived from the request itself."""
    return int.from_bytes(_digest(*parts)[:8], "big") / float(1 << 64)


def _distribution(options, preferred):
    """A distribution whose argmax is `preferred` and whose values sum to 1."""
    rest = [name for name in options if name != preferred]
    if not rest:
        return {preferred: 1.0}
    share = round(0.28 / len(rest), 4)
    values = {name: share for name in rest}
    values[preferred] = round(1.0 - share * len(rest), 4)
    return values


def _confidence(values):
    """The concentration measure this project verified against saved answers."""
    if len(values) < 2:
        return 1.0
    return round(max(0.0, min(1.0, (len(values) * max(values.values()) - 1) / (len(values) - 1))), 4)


def answer_question(key, question, state):
    """One synthetic answer that satisfies the lab's response validator."""
    kind = question["type"]
    if kind == "noul":
        if "address" in key:
            return {"type": "noul", "noul": 0.92}  # A demo turn should reach its verdict.
        return {"type": "noul", "noul": round(0.35 + 0.6 * _unit(key, state), 4)}
    criteria = question["criteria"]
    if kind == "choice":
        options = list(criteria)
        preferred = PREFERRED.get(key)
        preferred = preferred if preferred in options else options[0]
        values = _distribution(options, preferred)
        return {"type": "choice", "choice": preferred, "confidence": _confidence(values),
                "probabilities": values}
    levels = [str(i) for i in range(len(criteria))]
    preferred = levels[min(len(levels) - 1, int(_unit(key, state) * len(levels)))]
    values = _distribution(levels, preferred)
    return {"type": "score", "score": round(sum(int(k) * v for k, v in values.items()), 4),
            "confidence": _confidence(values), "probabilities": values,
            "legend": {level: str(criteria[int(level)]) for level in levels}}


class DemoJudge:
    """Answers every question locally. Never opens a socket, never needs a key."""

    def __init__(self):
        self.calls = []

    async def ask(self, state, questions, directory, emit, cancel_event):
        self.calls.append({"state": state, "questions": questions})
        directory.mkdir(parents=True, exist_ok=True)
        request = {"model": SYNTHETIC_MODEL, "state": state, "questions": questions}
        (directory / "request.json").write_text(
            json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        response = {"model": SYNTHETIC_MODEL, "synthetic": True,
                    "answers": {key: answer_question(key, question, state)
                                for key, question in questions.items()},
                    "usage": {"input_tokens": 0, "output_tokens": 0}}
        (directory / "response.json").write_text(
            json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
        response["_elapsed_ms"] = 0.0
        return response


def _placeholder(name, limit):
    text = {"title": "Demo task: a small utility with a test",
            "goal": "Show the agent's full turn with no Codex and no Jev key.",
            "message": "Demo mode: answers synthesised locally, no model was called.",
            "answer": "Demo answer: the turn ran through route, context, worker, checks and stopping rules."}.get(name)
    return (text or ("demo: " + name))[:limit]


def synthesize(schema, name="value"):
    """A minimal instance of the JSON Schema subset the agent asks workers for."""
    if "anyOf" in schema:
        chosen = next((option for option in schema["anyOf"] if option.get("type") != "null"),
                      schema["anyOf"][0])
        return synthesize(chosen, name)
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object":
        properties = schema.get("properties", {})
        keys = schema.get("required") or list(properties)
        return {key: synthesize(properties.get(key, {"type": "string"}), key) for key in keys}
    if kind == "array":
        count = max(int(schema.get("minItems", 0)), 1)
        count = min(count, int(schema.get("maxItems", count)))
        item = schema.get("items", {"type": "string"})
        return [synthesize(item, name) for _ in range(count)]
    if kind == "number" or kind == "integer":
        return 0
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return _placeholder(name, int(schema.get("maxLength", 200)))


class DemoWorker:
    """Stands in for Codex: same call signature, same events, same artifacts.

    It writes only inside the session's own workspace, and only two clearly
    named files, so the checks stage has something real to execute.
    """

    def __init__(self):
        self.calls = []

    def _intake(self, schema):
        """Walk a real guided round: first ask, then propose a plan.

        The intake contract is stricter than its JSON Schema (snake_case ids,
        distinct option labels, fields that must be empty for the chosen kind),
        so this branch is written out rather than synthesized from the schema.
        """
        properties = schema.get("properties") if isinstance(schema, dict) else None
        if not properties or "kind" not in properties:
            return synthesize(schema)
        if sum(1 for call in self.calls if call["schema"]) <= 1:
            return {
                "kind": "questions",
                "message": "Demo mode: questions asked locally, no planner was called.",
                "questions": [
                    {"id": "scope", "header": "Scope",
                     "question": "How broad should the work be?",
                     "options": [{"label": "Minimal example",
                                  "description": "One file and a test for it."},
                                 {"label": "Full module",
                                  "description": "Several files, tests and a run command."}]},
                    {"id": "output_form", "header": "Output",
                     "question": "What should the output be?",
                     "options": [{"label": "Code in the project",
                                  "description": "The agent creates and changes files."},
                                 {"label": "Explanation",
                                  "description": "Analysis only, no file changes."}]}],
                "plan": None, "answer": ""}
        return {
            "kind": "plan",
            "message": "Demo mode: plan made locally, no planner was called.",
            "questions": [], "answer": "",
            "plan": {"title": "Demo task: a utility with a test",
                     "goal": "Show the agent's full turn with no Codex and no Jev key.",
                     "deliverables": ["File demo_tool.py", "File test_demo_tool.py"],
                     "steps": ["Create the utility", "Create the test", "Run the checks"],
                     "acceptance": ["The project tests pass"],
                     "constraints": ["Standard library only"],
                     "assumptions": ["Answers synthesised locally, no model was called"],
                     "out_of_scope": ["Network and installing dependencies"]}}

    async def run(self, prompt, workspace, directory, emit, cancel_event,
                  readonly=False, schema=None):
        self.calls.append({"readonly": readonly, "schema": bool(schema)})
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
        (directory / "stderr.txt").write_text("", encoding="utf-8")
        events = directory / "events.jsonl"

        def record(event):
            with events.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

        record({"type": "turn.started", "demo": True})
        if schema:
            text = json.dumps(self._intake(schema), ensure_ascii=False)
        else:
            emit("plan", steps=[{"id": "1", "title": "Read the request", "completed": True},
                                {"id": "2", "title": "Change the project" if not readonly else "Inspect the project",
                                 "completed": True}])
            written = []
            if not readonly:
                for filename, content in (("demo_tool.py", DEMO_TOOL), ("test_demo_tool.py", DEMO_TEST)):
                    path = workspace / filename
                    if not path.exists():
                        path.write_text(content, encoding="utf-8")
                        written.append(filename)
            call_id = "%s:%s:demo" % (directory.parent.name, directory.name)
            command = "python -m unittest discover -v" if not readonly else "ls -R"
            emit("tool", kind="command_execution", command=command, status="running",
                 output="", exit_code=None, item_id="demo", call_id=call_id, lifecycle="started")
            emit("tool", kind="command_execution", command=command, status="completed",
                 output="demo mode: no command was run, the harness runs the checks",
                 exit_code=0, item_id="demo", call_id=call_id, lifecycle="completed")
            text = ("Demo mode: Codex was not called. " + (
                "Files created: " + ", ".join(written) + ". The real harness will check them."
                if written else "No files changed; this is a read-only turn."))
            emit("message", role="assistant", text=text)
        record({"type": "turn.completed", "demo": True})
        (directory / "final.txt").write_text(text, encoding="utf-8")
        return {"text": text, "usage": {"input_tokens": 0, "output_tokens": 0}, "completed": True}
