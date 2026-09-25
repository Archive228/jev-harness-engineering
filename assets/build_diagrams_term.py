# -*- coding: utf-8 -*-
"""The English article's diagrams, drawn as terminal output.

Same nine subjects as before, same numbers, none of them a drawing any more: every
one is a character grid in the interface's palette, so a diagram and the screenshot
under it read as the same object.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from termcanvas import Term, C  # noqa: E402

W = 118
made = []


def head(t, row=0, col=0, width=W, caption=None):
    t.rule(row, col, width, caption)


# ── 01. The call ──────────────────────────────────────────────────────────────
t = Term(W, 17, "jev · one call", chrome=True,
         desc="The application sends state and questions. Jev returns a typed Choice, Score or "
              "Noul answer. Ordinary code decides what happens next.")
t.rule(0, 0, W, "meaning in, a typed answer out, your code acts")
P = 26
for i, (col, title) in enumerate([(0, "INPUT"), (30, "JEV"), (60, "ANSWER"), (90, "YOUR CODE")]):
    t.panel(2, col, P, 12, title)
t.put(3, 2, "state", fill=C["ink"], weight=700)
t.put(4, 2, "  text, JSON, facts", fill=C["muted"])
t.put(5, 2, "  and the context", fill=C["muted"])
t.put(7, 2, "questions", fill=C["ink"], weight=700)
t.put(8, 2, "  instructions and", fill=C["muted"])
t.put(9, 2, "  criteria per answer", fill=C["muted"])
t.put(5, 34, "judges the", fill=C["ink"])
t.put(6, 34, "questions you", fill=C["ink"])
t.put(7, 34, "set, and only", fill=C["ink"])
t.put(8, 34, "those", fill=C["muted"])
for r, (name, what) in enumerate([("Choice", "one option from a list"),
                                  ("Score", "a place on your scale"),
                                  ("Noul", "the probability of yes")]):
    t.put(3 + r * 3, 62, name, fill=C["accent"], weight=700)
    t.put(4 + r * 3, 62, what, fill=C["muted"])
for r, act in enumerate(["store the category", "sort the queue", "pick a handler",
                         "run a check", "stop with a reason"]):
    t.put(3 + r * 2, 92, act, fill=C["ink"])
for col in (27, 57, 87):
    t.arrow_right(7, col)
t.rule(15, 0, W)
t.put(16, 0, "  The contract fixes the shape of the answer. Whether the judgement is right is a "
             "separate question.", fill=C["accent"])
made.append(t.save("01-jev-interface-en.svg"))


# ── 02. Three primitives on one message ───────────────────────────────────────
t = Term(W, 26, "jev · three primitives", chrome=True,
         desc="One support message asked three independent questions: a Choice of category, a "
              "Score of impact on a given scale, and a Noul on whether a workaround was stated.")
t.rule(0, 0, W, "one state, three independent questions")
t.panel(2, 0, W, 4, "SHARED STATE")
t.put(3, 3, '"PDF export fails in Safari. The same document exports in Chrome.', fill=C["ink"])
t.put(4, 3, ' I use Chrome for now, but I want the Safari export back."', fill=C["ink"])
for col in (18, 58, 98):
    t.arrow_down(6, col)
P = 38
for col, name in ((0, "CHOICE"), (40, "SCORE"), (80, "NOUL")):
    t.panel(7, col, P, 17, name)

t.put(8, 2, "Which option fits?", fill=C["ink"], weight=700)
t.put(9, 2, "Which category does this", fill=C["muted"])
t.put(10, 2, "message belong to?", fill=C["muted"])
for r, opt in enumerate(["export", "account", "payment", "other"]):
    t.runs(12 + r, 2, [("○ ", C["line"]), (opt, C["ink"])])
t.rule(17, 2, 34)
t.put(18, 2, "answer shape", fill=C["muted"])
t.put(19, 2, "ID + distribution", fill=C["ink"], weight=700)
t.put(20, 2, "+ confidence", fill=C["ink"], weight=700)
t.put(22, 2, "code: pick a queue", fill=C["dim"])

t.put(8, 42, "Where on the scale?", fill=C["ink"], weight=700)
t.put(9, 42, "How much does this block", fill=C["muted"])
t.put(10, 42, "the task?", fill=C["muted"])
for r, (lvl, txt) in enumerate([("0", "cosmetic defect"), ("1", "broken, workaround exists"),
                                ("2", "blocked, no workaround")]):
    t.runs(12 + r, 42, [(lvl + "  ", C["accent"]), (txt, C["ink"])])
t.rule(17, 42, 34)
t.put(18, 42, "answer shape", fill=C["muted"])
t.put(19, 42, "a value between levels", fill=C["ink"], weight=700)
t.put(20, 42, "+ distribution + confidence", fill=C["ink"], weight=700)
t.put(22, 42, "code: sort by impact", fill=C["dim"])

t.put(8, 82, "Is the statement true?", fill=C["ink"], weight=700)
t.put(9, 82, "Does the message state a", fill=C["muted"])
t.put(10, 82, "working workaround?", fill=C["muted"])
t.runs(12, 82, [("0", C["muted"]), ("──────────", C["line"]), ("0.5", C["accent"]),
                ("──────────", C["line"]), ("1", C["muted"])])
t.put(13, 82, "no", fill=C["dim"])
t.put(13, 107, "yes", fill=C["dim"])
t.put(14, 87, "0.5 means uncertainty", fill=C["muted"])
t.rule(17, 82, 34)
t.put(18, 82, "answer shape", fill=C["muted"])
t.put(19, 82, "P(yes): 0…1", fill=C["ink"], weight=700)
t.put(20, 82, "no separate confidence", fill=C["ink"], weight=700)
t.put(22, 82, "code: decide whether to ask", fill=C["dim"])

t.put(25, 0, "  The questions in one request are independent. The application code combines the "
             "answers.", fill=C["accent"])
made.append(t.save("02-three-primitives-en.svg"))


# ── 03. Three builds ──────────────────────────────────────────────────────────
t = Term(W, 22, "jev · three builds", chrome=True,
         desc="Build one uses Noul to relate evidence to a requirement. Build two uses Choice to "
              "pick an optional diagnostic. Build three ties them to a worker, and code decides "
              "when the run ends.")
t.rule(0, 0, W, "input, one narrow question, an observable result")
rows = [
    ("01", "Evidence report", "criteria, snapshot,", "command results", "Noul",
     "Is this evidence related", "to the requirement?", "evidence-report.json",
     "passed · failed · unverified",
     "Noul is an annotation. Code sets the statuses from fresh results."),
    ("02", "Next-check router", "a failed check,", "the diagnostic registry", "Choice",
     "Which extra check is", "useful right now?", "next-check.json",
     "an ID from the registry, or a refusal",
     "Code runs the mandatory checks. Jev picks the extra one."),
    ("03", "Bounded loop", "a new snapshot,", "the report and limits", "Noul + Choice",
     "Related to the requirement?", "What to check next?", "run-report.md",
     "complete, or stopped with a reason",
     "Code ends the loop only when acceptance holds. Limits cap the attempts."),
]
for i, (n, title, a, b, prim, q1, q2, out, res, note) in enumerate(rows):
    r = 2 + i * 6
    t.panel(r, 0, W, 6)
    t.runs(r + 1, 2, [(f" {n} ", C["accent"]), ("  ", None), (title, C["ink"])])
    t.put(r + 2, 3, a, fill=C["muted"])
    t.put(r + 3, 3, b, fill=C["muted"])
    t.arrow_right(r + 2, 30)
    t.put(r + 1, 36, f"jev · {prim}", fill=C["accent"], weight=700)
    t.put(r + 2, 36, q1, fill=C["ink"])
    t.put(r + 3, 36, q2, fill=C["ink"])
    t.arrow_right(r + 2, 68)
    t.put(r + 1, 74, out, fill=C["accent2"], weight=700)
    t.put(r + 2, 74, res, fill=C["muted"])
    t.put(r + 4, 3, note, fill=C["dim"])
t.put(21, 0, "  Jev returns a judgement or an ID. The application runs the checks, the repairs and "
             "the stop.", fill=C["accent"])
made.append(t.save("03-three-builds-en.svg"))


# ── 04. One run, step by step ─────────────────────────────────────────────────
t = Term(W, 20, "jev · one run", chrome=True,
         desc="An offline demonstration: a requirement is unverified, the mandatory check C2 "
              "fails, a prepared router answer picks diagnostic D2, the worker repairs the code, "
              "a new snapshot is taken, both checks pass and the policy ends the run.")
t.rule(0, 0, W, "from unverified to a confirmed result")
steps = [
    ("01", "EVIDENCE", "R2: search by description",
     "a worker claim exists, no fresh C2 result", "UNVERIFIED", C["warn"]),
    ("02", "MANDATORY", "code runs C2",
     "search by description finds nothing", "FAIL", C["fail"]),
    ("03", "DIAGNOSTIC", "demo router picks D2",
     "only the title field was sent", "NEW FACT", C["accent"]),
    ("04", "REPAIR", "the worker updates the code",
     "search matches title OR description", "NEW CODE", C["ink"]),
    ("05", "RECHECK", "new snapshot, C1 and C2",
     "old results cannot confirm new code", "PASS PASS", C["ok"]),
    ("06", "RULE", "every mandatory condition holds",
     "the program saves the report and stops", "COMPLETE", C["ok"]),
]
for i, (n, kind, what, why, status, col) in enumerate(steps):
    r = 2 + i * 3
    t.runs(r, 0, [(f" {n} ", C["accent"]), ("  ", None), (kind.ljust(12), C["muted"]),
                  (what, C["ink"])])
    t.put(r + 1, 8, why, fill=C["dim"])
    t.put(r, 92, status.rjust(10), fill=col, weight=700)
    if i < len(steps) - 1:
        t.put(r + 2, 2, "│", fill=C["line"])
t.rule(19 - 1, 0, W)
t.put(19, 0, "  No result is not a failure. A pass on the old version is not a pass on this one.",
      fill=C["accent"])
made.append(t.save("04-run-trace-en.svg"))


# ── 05. Reading an answer ─────────────────────────────────────────────────────
t = Term(W, 20, "jev · reading an answer", chrome=True,
         desc="What to look at in each primitive: the distribution for Choice, the legend for "
              "Score, and the single number for Noul.")
t.rule(0, 0, W, "the label is the least useful field")
for col, name in ((0, "CHOICE"), (40, "SCORE"), (80, "NOUL")):
    t.panel(2, col, 38, 15, name)
t.put(3, 2, "probabilities", fill=C["ink"], weight=700)
for r, (k, v) in enumerate([("export", 1.0), ("account", 0.0), ("payment", 0.0), ("other", 0.0)]):
    t.put(5 + r, 2, k.ljust(9), fill=C["muted"])
    t.bar(5 + r, 11, 14, v)
    t.put(5 + r, 28, f"{v:.1f}", fill=C["ink"])
t.rule(10, 2, 34)
t.put(11, 2, "choice is the argmax.", fill=C["muted"])
t.put(12, 2, "Two different states give", fill=C["muted"])
t.put(13, 2, "one label: {0.4, 0.35, 0.25}", fill=C["muted"])
t.put(14, 2, "is nearly a coin flip.", fill=C["muted"])

t.put(3, 42, "legend", fill=C["ink"], weight=700)
for r, (k, v) in enumerate([("0", "cosmetic"), ("1", "workaround exists"), ("2", "task is blocked")]):
    t.runs(5 + r, 42, [(k + "  ", C["accent"]), (v, C["ink"])])
t.rule(9, 42, 34)
t.put(10, 42, "score 1.0", fill=C["accent"], weight=700)
t.put(12, 42, "an index into the legend,", fill=C["muted"])
t.put(13, 42, "not a fraction of a scale.", fill=C["muted"])
t.put(14, 42, "A fractional value sits", fill=C["muted"])
t.put(15, 42, "between two levels.", fill=C["muted"])

t.put(3, 82, "noul", fill=C["ink"], weight=700)
t.put(5, 82, "0.95", fill=C["accent"], weight=700)
t.bar(6, 82, 26, 0.95)
t.rule(8, 82, 34)
t.put(9, 82, "one number: the", fill=C["muted"])
t.put(10, 82, "probability that the", fill=C["muted"])
t.put(11, 82, "statement holds.", fill=C["muted"])
t.put(13, 82, "no distribution and no", fill=C["muted"])
t.put(14, 82, "confidence to read.", fill=C["muted"])
t.put(19, 0, "  The information lives in the distribution, not in the label above it.",
      fill=C["accent"])
made.append(t.save("05-answer-layers-en.svg"))


# ── 06. The phrasing decides ──────────────────────────────────────────────────
t = Term(W, 16, "jev · the question is the engineering", chrome=True,
         desc="The same ticket and the same meaning. Demanding explicitness moves the answer by "
              "six hundredths, and at a gate of 0.9 that is a different branch of the program.")
t.rule(0, 0, W, "one ticket, one meaning, two phrasings")
t.panel(2, 0, W, 4, "STATE")
t.put(3, 3, "PDF export fails in Safari. The same document exports in Chrome.", fill=C["ink"])
t.put(4, 3, "I use Chrome for now.", fill=C["ink"])
for col, tag, q, val in ((0, "LOOSE", "Is a working workaround mentioned", "0.95"),
                         (60, "STRICT", "Does the message explicitly state", "0.89")):
    t.panel(7, col, 56, 7, tag)
    t.put(8, col + 2, q, fill=C["ink"])
    t.put(9, col + 2, "in the message?" if col == 0 else "a working workaround?", fill=C["ink"])
    t.runs(11, col + 2, [("noul ", C["muted"]), (val, C["accent"])])
    t.bar(11, col + 14, 26, float(val))
t.put(12, 62, "the word explicitly", fill=C["dim"])
t.put(15, 0, "  Six hundredths. At a threshold of 0.9 the same data goes down different branches.",
      fill=C["accent"])
made.append(t.save("06-phrasing-en.svg"))


# ── 07. What gets built on it ─────────────────────────────────────────────────
t = Term(W, 22, "jev · one call shape", chrome=True,
         desc="Different products on one call shape. What they share is that the program builds "
              "the option set and the model picks from a closed list.")
t.rule(0, 0, W, "the program builds the options, the model picks")
items = [
    ("Browser actions", "DOM becomes a numbered table", "Choice returns an index"),
    ("Context compaction", "one tool call", "two Nouls: keep the call, keep the output"),
    ("Model routing", "task features", "three independent Choices, one request"),
    ("Graph traversal", "candidate edges", "the distribution becomes hypothesis scores"),
    ("Review triage", "a file by dimension matrix", "five Nouls in one round trip"),
    ("Completion check", "the answer text", "a Noul on a narrow fact, not on quality"),
]
for i, (name, inp, out) in enumerate(items):
    r = 2 + i * 3
    t.runs(r, 0, [("├─ ", C["line"]), (name.ljust(20), C["accent"])])
    t.put(r, 23, "in:  " + inp, fill=C["muted"])
    t.put(r + 1, 23, "out: " + out, fill=C["ink"])
t.put(20, 0, "  Jev picks from a closed set you assembled. What it cannot propose never enters it.",
      fill=C["accent"])
made.append(t.save("07-applications-en.svg"))


# ── 08. The screen ────────────────────────────────────────────────────────────
t = Term(W, 26, "jevis · the screen", chrome=True,
         desc="A map of the agent's interface: the header carries the state and the project, the "
              "left column the checks and the decision, the right drawer the event stream, and "
              "the bottom row the message box and the modes.")
t.rule(0, 0, W, "where everything is")
SCREEN = 70
t.panel(2, 0, SCREEN, 22)
t.runs(3, 2, [("JEVIS / HARNESS", C["accent"]), ("   ·   Ready for a message", C["muted"])])
t.put(4, 2, "/tmp/jevis-demo/…/workspace", fill=C["dim"])
c = 2
for tab in ("New", "Sessions", "Files", "JEVIS", "Logs", "Menu"):
    t.put(5, c, f" {tab} ", fill=C["accent"])
    c += len(tab) + 4
t.rule(6, 2, SCREEN - 4)
t.put(7, 3, "CHECKS", fill=C["ok"], weight=700)
t.put(8, 3, "1 / 6 passed", fill=C["ink"])
t.put(9, 3, "× UTC ordering", fill=C["muted"])
t.put(10, 3, "✓ JSON and Markdown reports", fill=C["muted"])
t.put(12, 3, "JEV", fill=C["accent"], weight=700)
t.put(13, 3, "next_action → finish · 0.58", fill=C["ink"])
t.put(15, 3, "POLICY", fill=C["fail"], weight=700)
t.put(16, 3, "finishing is blocked by code", fill=C["ink"])
t.put(7, 40, "JEVIS · LIVE LOGS", fill=C["accent"], weight=700)
t.runs(8, 40, [("Jev  Checks  ", C["muted"]), ("Events", C["accent"])])
for r, ln in enumerate(['"jev_calls": 5,', '"worker_calls": 2,', '"checks": 18,',
                        '"usage_complete": true']):
    t.put(10 + r, 40, ln, fill=C["dim"])
t.panel(18, 2, SCREEN - 4, 3)
t.put(19, 4, "Your message", fill=C["muted"])
c = 3
for b in ("Discuss ▾", "Execute ▾", "Jev: assist ▾", "Send ↵"):
    t.put(22, c, f" {b} ", fill=C["accent"])
    c += len(b) + 4
notes = [
    (3, "state and project", "what it is doing, and where it may write"),
    (7, "checks", "the requirements a command just confirmed"),
    (12, "jev", "the decision, and how concentrated it was"),
    (15, "policy", "what the code did with that decision"),
    (7, "live logs", "the event stream as it reaches the disk"),
    (19, "message and modes", "discuss or direct, execute or plan, Jev off"),
]
for i, (anchor, title, body) in enumerate(notes):
    r = 3 + i * 4
    t.put(r, SCREEN + 1, "◄", fill=C["accent"])
    t.runs(r, SCREEN + 3, [(f"{i + 1} ", C["accent"]), (title, C["ink"])])
    t.put(r + 1, SCREEN + 5, body, fill=C["muted"])
t.put(25, 0, "  Every number here was written to a file first. Nothing on this screen is a guess.",
      fill=C["accent"])
made.append(t.save("08-agent-map-en.svg"))


# ── 09. One stopped turn ──────────────────────────────────────────────────────
t = Term(W, 24, "jevis · one stopped turn", chrome=True,
         desc="The worker claims the work is done, the checks produce facts, Jev returns a "
              "decision with a confidence, and only the policy ends the turn.")
t.rule(0, 0, W, "four inputs, one decision, and only code decides")
cols = [
    (0, "WORKER", "claims the work is done", ['"No files changed;', 'this is a read-only turn."'],
     C["muted"]),
    (40, "CHECKS", "run and produce facts", ["1 of 6 passed", "C2 still fails"], C["ok"]),
    (80, "JEV", "returns a decision", ["next_action → finish", "confidence 0.58"], C["accent"]),
]
for col, title, sub, body, colour in cols:
    t.panel(2, col, 38, 7, title, title_fill=colour)
    t.put(3, col + 2, sub, fill=C["muted"])
    t.rule(4, col + 2, 34)
    for i, ln in enumerate(body):
        t.put(5 + i, col + 2, ln, fill=C["ink"])
for col in (18, 58, 98):
    t.arrow_down(9, col)
# POLICY spans the whole width so all three arrows land inside it: the decision it
# makes is over every input at once, not over the two on the left.
t.panel(10, 0, W, 5, "POLICY", title_fill=C["accent"])
t.put(11, 2, "A check failed or is stale: finishing is blocked by code.", fill=C["ink"])
t.put(12, 2, "Rule 1 of five. The confidence never entered this comparison.", fill=C["dim"])
t.arrow_down(15, 58)
t.panel(16, 39, 40, 4, "STOPPED", title_fill=C["fail"])
t.put(17, 41, "with a reason, and a way to carry on", fill=C["muted"])
t.dots(20, 0)
t.put(22, 0, "  Swap the model for one that always answers finish and this turn still stops.",
      fill=C["accent"])
made.append(t.save("09-stop-anatomy-en.svg"))

print("done: " + ", ".join(made))
