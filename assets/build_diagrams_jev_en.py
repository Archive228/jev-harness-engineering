# -*- coding: utf-8 -*-
"""English versions of the Jev-first diagrams. Same numbers, same saved answers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_diagrams import SVG, C  # noqa: E402


s = SVG(1480, 800, 'How one Jev answer is read, layer by layer',
        'Choice: the distribution matters, the label is its argmax. Score: the legend matters, the '
        'number is a level index. Noul: one number, no distribution and no confidence.')
s.head('05', 'Reading an answer', 'What to look at in each primitive',
       'The label is the least useful field. The information lives in the distribution.')

s.rect(64, 232, 430, 488, stroke=C['line'])
s.tag(88, 256, 132, 'CHOICE')
s.text(88, 336, 'probabilities', size=30, weight=700)
s.lines(88, 378, ['export  1.0', 'account 0.0', 'payment 0.0', 'other   0.0'], size=23, dy=34)
s.line(88, 528, 470, 528)
s.lines(88, 572, ['choice is the argmax.', 'Two different situations', 'give the same label:',
                  '{0.4, 0.35, 0.25} is a coin flip.'], size=21, dy=32, fill=C['muted'])

s.rect(524, 232, 430, 488, stroke=C['line'])
s.tag(548, 256, 118, 'SCORE')
s.text(548, 336, 'legend', size=30, weight=700)
s.lines(548, 378, ['0  cosmetic', '1  workaround exists', '2  task is blocked'], size=23, dy=34)
s.line(548, 494, 930, 494)
s.text(548, 540, 'score 1.0', size=28, weight=700, fill=C['accent'])
s.lines(548, 578, ['A level index,', 'not a fraction of the scale.', 'A fractional value is a position',
                   'between levels, not a label.'], size=21, dy=32, fill=C['muted'])

s.rect(984, 232, 432, 488, stroke=C['line'])
s.tag(1008, 256, 108, 'NOUL')
s.text(1008, 336, 'noul', size=30, weight=700)
s.text(1008, 386, '0.95', size=56, weight=700, fill=C['accent'])
s.line(1008, 430, 1392, 430)
s.lines(1008, 476, ['One number: the probability', 'that the statement holds.',
                    '', 'No distribution, no confidence —', 'nothing to read but itself.'],
        size=21, dy=32, fill=C['muted'])
s.save('05-answer-layers-en.svg')


s = SVG(1480, 700, 'One phrasing says 0.95, another says 0.89',
        'The same ticket and the same meaning. Demanding explicitness moves the answer by six '
        'hundredths, and at a gate of 0.9 that is a different branch of the program.')
s.head('06', 'Jev engineering', 'The question is the engineering',
       'One ticket, one state, one meaning. Two phrasings, two answers.')

s.rect(64, 226, 1352, 104, fill=C['soft'], stroke=C['line'])
s.text(88, 268, 'state', size=20, weight=700, fill=C['muted'])
s.text(88, 304, 'PDF export fails in Safari. The same document exports in Chrome. I use Chrome for now.',
       size=22)

s.rect(64, 370, 660, 250, stroke=C['line'])
s.tag(88, 396, 128, 'LOOSE')
s.lines(88, 470, ['Is a working workaround', 'mentioned in the message?'], size=23, dy=33)
s.text(88, 576, 'noul 0.95', size=40, weight=700, fill=C['accent'])

s.rect(756, 370, 660, 250, stroke=C['line'])
s.tag(780, 396, 150, 'STRICT')
s.lines(780, 470, ['Does the message explicitly', 'state a working workaround?'], size=23, dy=33)
s.text(780, 576, 'noul 0.89', size=40, weight=700, fill=C['accent'])
s.text(1050, 576, 'the word explicitly', size=22, fill=C['muted'])
s.save('06-phrasing-en.svg')


s = SVG(1480, 800, 'Six products built on the same call',
        'Six different products on one call shape. What they share: the program builds the option '
        'set and the model picks from a closed list.')
s.head('07', 'Applications', 'One call shape, different products',
       'The program builds the options. The model picks from a closed set and returns a distribution.')

items = [
    ('Browser agent', 'DOM to action table', 'Choice picks an index'),
    ('Compaction', 'one tool call', 'two Nouls: keep call, keep output'),
    ('Model routing', 'task features', 'three independent Choices, one request'),
    ('Graph traversal', 'candidate edges', 'distribution as hypothesis scores'),
    ('Review triage', 'file x dimension', 'five Nouls in one round trip'),
    ('Verification', 'the answer text', 'Noul on a narrow fact, not on quality'),
]
for i, (title, inp, out) in enumerate(items):
    x = 64 + (i % 3) * 452
    y = 240 + (i // 3) * 268
    s.rect(x, y, 428, 232, stroke=C['line'])
    s.text(x + 24, y + 62, title, size=28, weight=700)
    s.text(x + 24, y + 108, 'in: ' + inp, size=21, fill=C['muted'])
    s.line(x + 24, y + 134, x + 404, y + 134)
    s.lines(x + 24, y + 176, [out[:36], out[36:]] if len(out) > 36 else [out], size=21, dy=30)
s.save('07-applications-en.svg')

print('done: 05-answer-layers-en.svg, 06-phrasing-en.svg, 07-applications-en.svg')
