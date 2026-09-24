# -*- coding: utf-8 -*-
"""English versions of diagrams 01-04.

build_diagrams.py draws these with Russian labels, and the English article was
shipping those Russian images. Same geometry and same palette here, English text,
with wording kept short so nothing overflows its box.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_diagrams import SVG, C, MONO, ROOT  # noqa: E402


# ── 01. The interface ─────────────────────────────────────────────────────────
s = SVG(1480, 760, 'How the Jev interface works',
        'The application sends state and questions. Jev returns typed Choice, Score and Noul '
        'answers. The application code decides the next action. The diagram shows the API '
        'contract, not the internals of the network.')
s.head('01', 'Interface', 'Meaning → typed answer → action',
       'You define the answer space. Jev judges meaning. The program acts.')
s.rect(64, 232, 312, 352, stroke=C['line'])
s.tag(88, 256, 118, 'INPUT')
s.text(88, 334, 'State', size=30, weight=700)
s.lines(88, 374, ['Text, JSON, facts', 'and needed context'], size=23, dy=32)
s.line(88, 431, 352, 431)
s.text(88, 477, 'Questions', size=30, weight=700)
s.lines(88, 517, ['Instructions + criteria', 'for each answer'], size=22, dy=31)
s.line(382, 408, 430, 408, stroke=C['muted'], arrow=True)
s.rect(440, 296, 228, 224, fill=C['pale'], stroke=C['accent'], sw=2)
s.text(554, 380, 'Jev', size=64, weight=700, anchor='middle')
s.lines(554, 427, ['Judges the', 'questions you set'], size=22, dy=31, anchor='middle')
s.line(676, 408, 724, 408, stroke=C['muted'], arrow=True)
s.rect(734, 232, 326, 352, stroke=C['line'])
s.tag(758, 256, 126, 'ANSWER')
s.text(758, 337, 'Choice', size=28, weight=700)
s.text(758, 370, 'One option from a list', size=22, fill=C['muted'])
s.text(758, 430, 'Score', size=28, weight=700)
s.text(758, 463, 'A position on a scale', size=22, fill=C['muted'])
s.text(758, 523, 'Noul', size=28, weight=700)
s.text(758, 556, 'Probability of yes', size=22, fill=C['muted'])
s.line(1068, 408, 1114, 408, stroke=C['muted'], arrow=True)
s.rect(1124, 232, 292, 352, fill=C['soft'])
s.tag(1148, 256, 152, 'APPLICATION', fill=C['paper'])
s.text(1148, 339, 'Ordinary code', size=28, weight=700)
s.lines(1148, 391, ['Store the category', 'Sort the queue', 'Pick a handler', 'Run a check'],
        size=21, dy=42)
s.rect(64, 626, 1352, 80, fill=C['pale'])
s.text(90, 660, 'The contract constrains the answer type. Whether the judgement is right is '
                'checked separately.', size=23, weight=700)
s.text(90, 689, 'This diagram describes the data exchanged with the API, not the model '
                'architecture.', size=19, fill=C['muted'])
s.save('01-jev-interface-en.svg')


# ── 02. Three primitives ──────────────────────────────────────────────────────
s = SVG(1480, 1080, 'Three Jev primitives on one message',
        'The same PDF export failure is sent to three independent questions. Choice picks a '
        'category, Score rates impact on a given scale from zero to two, Noul rates the '
        'probability that a working workaround is stated. Probability values and live API '
        'results are not shown.')
s.head('02', 'Three primitives', 'One state. Three different questions.',
       'Below: the criteria given and the answer shapes, with no invented API results.')
s.rect(64, 211, 1352, 140, stroke=C['line'])
s.tag(88, 232, 166, 'SHARED STATE')
s.lines(280, 252, ['"PDF export fails in Safari. The same document exports in Chrome.',
                   'I use Chrome for now, but I want the Safari export back."'], size=25, dy=40)
for x in [276, 740, 1204]:
    s.line(x, 351, x, 396, stroke=C['muted'], arrow=True)

xs = [64, 528, 992]
for i, x in enumerate(xs):
    s.rect(x, 406, 424, 572, stroke=C['line'])

# Choice
x = xs[0]
s.tag(x + 24, 430, 108, 'CHOICE', fill=C['pale'], ink=C['accent'])
s.text(x + 24, 505, 'Which option fits?', size=26, weight=700)
s.lines(x + 24, 550, ['Which category does', 'this message belong to?'], size=24, dy=33)
for y, label in [(615, 'export  ·  Export'), (657, 'account  ·  Account'),
                 (699, 'payment  ·  Payment'), (741, 'other  ·  Other')]:
    s.circle(x + 35, y - 7, 6, C['bg'], stroke=C['line'])
    s.text(x + 53, y, label, size=22)
s.line(x + 24, 773, x + 400, 773)
s.text(x + 24, 810, 'Answer shape', size=18, fill=C['muted'], weight=700)
s.lines(x + 24, 843, ['ID + distribution', '+ confidence'], size=24, dy=32, weight=700)
s.text(x + 24, 930, 'Code: pick a queue', size=22, fill=C['muted'])

# Score
x = xs[1]
s.tag(x + 24, 430, 108, 'SCORE', fill=C['pale'], ink=C['accent'])
s.text(x + 24, 505, 'Where on the scale?', size=26, weight=700)
s.lines(x + 24, 550, ['How much does this', 'block the task?'], size=24, dy=33)
s.line(x + 45, 623, x + 373, 623, stroke=C['ink'], sw=3)
for pos, v in [(x + 45, '0'), (x + 209, '1'), (x + 373, '2')]:
    s.circle(pos, 623, 6, C['accent'])
    s.text(pos, 656, v, size=23, anchor='middle', weight=700)
s.lines(x + 24, 694, ['0  Cosmetic defect', '1  Broken, workaround exists',
                      '2  Blocked, no workaround'], size=21, dy=31)
s.line(x + 24, 773, x + 400, 773)
s.text(x + 24, 810, 'Answer shape', size=18, fill=C['muted'], weight=700)
s.lines(x + 24, 843, ['A value between levels', '+ distribution + confidence'],
        size=22, dy=32, weight=700)
s.text(x + 24, 930, 'Code: sort by impact', size=22, fill=C['muted'])

# Noul
x = xs[2]
s.tag(x + 24, 430, 108, 'NOUL', fill=C['pale'], ink=C['accent'])
s.text(x + 24, 505, 'Is the statement true?', size=26, weight=700)
s.lines(x + 24, 550, ['Does the message state', 'a working workaround?'], size=24, dy=33)
s.line(x + 45, 623, x + 373, 623, stroke=C['ink'], sw=3)
for pos, v in [(x + 45, '0'), (x + 209, '0.5'), (x + 373, '1')]:
    s.circle(pos, 623, 6, C['bg'], stroke=C['ink'])
    s.text(pos, 656, v, size=23, anchor='middle', weight=700)
s.text(x + 45, 690, 'no', size=19, anchor='middle', fill=C['muted'])
s.text(x + 373, 690, 'yes', size=19, anchor='middle', fill=C['muted'])
s.text(x + 209, 734, '0.5 ≈ uncertainty', size=23, anchor='middle', fill=C['muted'])
s.line(x + 24, 773, x + 400, 773)
s.text(x + 24, 810, 'Answer shape', size=18, fill=C['muted'], weight=700)
s.lines(x + 24, 843, ['Probability of yes: 0…1', 'No separate confidence'],
        size=22, dy=32, weight=700)
s.text(x + 24, 930, 'Code: decide whether to ask', size=21, fill=C['muted'])
s.text(64, 1025, 'The questions in one request are independent. The application code combines '
                 'the answers.', size=24, weight=700)
s.save('02-three-primitives-en.svg')


# ── 03. Three small builds ────────────────────────────────────────────────────
s = SVG(1480, 1160, 'Jev in three small builds',
        'The first build uses Noul to judge evidence. The second uses Choice to pick an optional '
        'diagnostic from a registry. The third connects them to a worker and to programmatic '
        'transition rules. Mandatory checks, limits and the completion decision are set by code.')
s.head('03', 'Three small builds', 'Three tools. One contract with Jev.',
       'Input → one narrow question → answer → observable result.')
rows = [
    (219, '01', 'Evidence report', 'Criteria, snapshot,', 'command results', 'Noul',
     'Is this evidence related', 'to the requirement?', 'evidence-report.json',
     'passed · failed · unverified',
     'Noul is an annotation. Code sets the statuses from fresh test results.'),
    (502, '02', 'Next-check router', 'A failed check,', 'the diagnostic registry', 'Choice',
     'Which extra check', 'is useful right now?', 'next-check.json',
     'ID from the registry / refusal',
     'Code runs the mandatory checks. Jev picks the extra diagnostic.'),
    (785, '03', 'Bounded loop', 'A new snapshot,', 'the report and limits', 'Noul + Choice',
     'Related to the requirement?', 'What to check next?', 'run-report.md',
     'complete / stopped + reason',
     'Code ends the loop only when acceptance holds. Limits cap the attempts.'),
]
for y, n, title, a, b, primitive, q1, q2, out, result, caption in rows:
    s.rect(64, y, 1352, 252, stroke=C['line'])
    s.tag(88, y + 20, 56, n, fill=C['soft'])
    s.text(159, y + 46, title, size=28, weight=700)
    s.lines(88, y + 105, [a, b], size=25, dy=34)
    s.line(406, y + 118, 474, y + 118, stroke=C['muted'], arrow=True)
    s.rect(488, y + 70, 420, 108, fill=C['pale'])
    s.text(511, y + 101, f'Jev · {primitive}', size=20, fill=C['accent'], weight=700)
    s.lines(511, y + 134, [q1, q2], size=22, dy=29)
    s.line(922, y + 118, 986, y + 118, stroke=C['muted'], arrow=True)
    s.text(1004, y + 105, out, size=23, font=MONO, weight=700)
    s.text(1004, y + 144, result, size=20, fill=C['muted'])
    s.line(88, y + 196, 1392, y + 196)
    s.text(88, y + 229, caption, size=21, fill=C['muted'])
s.text(64, 1100, 'Jev returns a judgement or an ID. The application runs the checks, the repairs '
                 'and the stop.', size=24, weight=700)
s.save('03-three-builds-en.svg')


# ── 04. One run, step by step ─────────────────────────────────────────────────
s = SVG(1480, 1290, 'Trace of a demonstration run',
        'An explicitly offline scenario: the search-by-description requirement is unverified at '
        'first. The mandatory check C2 exposes the bug. A prepared router answer picks diagnostic '
        'D2. The worker fixes the implementation, a new snapshot is taken, both mandatory tests '
        'pass, and the programmatic policy ends the run. The diagram does not show live Jev API '
        'results.')
s.head('04', 'One run, step by step', 'From unverified to a confirmed result',
       'Offline demo: judge answers and the worker action are prepared. '
       'The live Jev API is not called here.')
s.line(98, 274, 98, 1120, stroke=C['line'], sw=3)
steps = [
    ('01', 'Evidence', 'R2: search by description',
     'A worker claim exists. There is no fresh C2 result yet.', 'UNVERIFIED'),
    ('02', 'Mandatory test', 'Code runs C2',
     'Search by description finds nothing. A failure is now a fact.', 'FAIL'),
    ('03', 'Extra diagnostic', 'Demo router → D2',
     'Query check: only the title field is used.', 'NEW FACT'),
    ('04', 'Repair', 'The worker updates the code',
     'Search matches title OR description.', 'NEW CODE'),
    ('05', 'Recheck', 'New snapshot → C1 and C2',
     'Results from the old version do not confirm the current code.', 'PASS + PASS'),
    ('06', 'Completion rule', 'Every mandatory condition holds',
     'The program saves the report and stops the loop.', 'COMPLETE'),
]
for i, (n, role, title, body, status) in enumerate(steps):
    y = 220 + i * 158
    s.circle(98, y + 55, 26, C['pale'], stroke=C['accent'])
    s.text(98, y + 63, n, size=21, weight=700, anchor='middle')
    s.rect(153, y, 1263, 132, stroke=C['line'])
    s.text(181, y + 30, role.upper(), size=15, weight=700, fill=C['muted'])
    s.text(181, y + 67, title, size=28, weight=700)
    s.text(181, y + 107, body, size=23, fill=C['muted'])
    s.tag(1187, y + 43, 205, status,
          fill=C['pale'] if i in [2, 5] else C['soft'],
          ink=C['accent'] if i in [2, 5] else C['ink'], size=17)
s.rect(64, 1208, 1352, 48, fill=C['pale'], radius=12)
s.text(88, 1239, 'No result ≠ failure. PASS on the old version ≠ PASS on the current one. '
                 'A Jev decision ≠ a command result.', size=22, weight=700)
s.save('04-run-trace-en.svg')

print('done: ' + ', '.join(p.name for p in sorted(ROOT.glob('0[1-4]*-en.svg'))))
