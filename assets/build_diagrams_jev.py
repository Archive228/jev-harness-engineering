# -*- coding: utf-8 -*-
"""Diagrams for the Jev-first edit. Same palette and helpers as build_diagrams.py.

Every number here comes from a saved answer in verification/, not from an example:
the layers diagram is first-call-ru/response.json, and the phrasing comparison is
that same ticket asked twice (0.95 vs 0.89).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_diagrams import SVG, C  # noqa: E402  (reuse the article's own builder)


# ── 05. Как читается один ответ ───────────────────────────────────────────────
s = SVG(1480, 800, 'Как читается ответ Jev по слоям',
        'У Choice главное поле — probabilities, метка это её аргмакс. У Score главное — legend, '
        'число это индекс уровня. У Noul одно число и нет ни распределения, ни confidence.')
s.head('05', 'Чтение ответа', 'Что смотреть у каждого примитива',
       'Метка — самое бесполезное поле ответа. Информация лежит в распределении.')

s.rect(64, 232, 430, 488, stroke=C['line'])
s.tag(88, 256, 132, 'CHOICE')
s.text(88, 336, 'probabilities', size=30, weight=700)
s.lines(88, 378, ['export  1.0', 'account 0.0', 'payment 0.0', 'other   0.0'], size=23, dy=34)
s.line(88, 528, 470, 528)
s.lines(88, 572, ['choice — это аргмакс.', 'Две разных ситуации дают', 'одну и ту же метку:',
                  '{0.4, 0.35, 0.25} — почти монетка.'], size=21, dy=32, fill=C['muted'])

s.rect(524, 232, 430, 488, stroke=C['line'])
s.tag(548, 256, 118, 'SCORE')
s.text(548, 336, 'legend', size=30, weight=700)
s.lines(548, 378, ['0  косметика', '1  есть обход', '2  задача заблокирована'], size=23, dy=34)
s.line(548, 494, 930, 494)
s.text(548, 540, 'score 1.0', size=28, weight=700, fill=C['accent'])
s.lines(548, 578, ['Это индекс уровня,', 'а не доля от шкалы.', 'Дробное значение — положение',
                   'между уровнями, а не метка.'], size=21, dy=32, fill=C['muted'])

s.rect(984, 232, 432, 488, stroke=C['line'])
s.tag(1008, 256, 108, 'NOUL')
s.text(1008, 336, 'noul', size=30, weight=700)
s.text(1008, 386, '0.95', size=56, weight=700, fill=C['accent'])
s.line(1008, 430, 1392, 430)
s.lines(1008, 476, ['Одно число — вероятность', 'того, что утверждение верно.',
                    '', 'Ни распределения, ни confidence:',
                    'читать нечего, кроме него самого.'], size=21, dy=32, fill=C['muted'])
s.save('05-answer-layers.svg')

# ── 06. Формулировка решает ───────────────────────────────────────────────────
s = SVG(1480, 700, 'Одна формулировка даёт 0.95, другая 0.89',
        'Один и тот же тикет и один и тот же смысл вопроса. Разница в требовании явности '
        'меняет ответ на шесть сотых, и при пороге 0.9 это разные ветки программы.')
s.head('06', 'Jev engineering', 'Вопрос — это и есть инженерия',
       'Один тикет, один state, один смысл. Две формулировки — два ответа.')

s.rect(64, 226, 1352, 104, fill=C['soft'], stroke=C['line'])
s.text(88, 268, 'state', size=20, weight=700, fill=C['muted'])
s.text(88, 304, 'В Safari экспорт PDF завершается ошибкой. В Chrome тот же документ экспортируется.',
       size=22)

s.rect(64, 370, 660, 250, stroke=C['line'])
s.tag(88, 396, 128, 'МЯГКО')
s.lines(88, 470, ['Указан ли в обращении', 'рабочий обход проблемы?'], size=23, dy=33)
s.text(88, 576, 'noul 0.95', size=40, weight=700, fill=C['accent'])

s.rect(756, 370, 660, 250, stroke=C['line'])
s.tag(780, 396, 150, 'СТРОГО')
s.lines(780, 470, ['Does the message explicitly', 'state a working workaround?'], size=23, dy=33)
s.text(780, 576, 'noul 0.89', size=40, weight=700, fill=C['accent'])
s.text(1050, 576, '← слово explicitly', size=22, fill=C['muted'])
s.save('06-phrasing.svg')

# ── 07. Что на этом строят ────────────────────────────────────────────────────
s = SVG(1480, 800, 'Что построено на том же вызове',
        'Шесть разных продуктов на одной форме обращения. Общее в них одно: набор вариантов '
        'строит программа, а модель выбирает из закрытого набора.')
s.head('07', 'Применения', 'Одна форма вызова, разные продукты',
       'Варианты строит программа. Модель выбирает из закрытого набора и возвращает распределение.')

items = [
    ('Браузерный агент', 'DOM → таблица действий', 'Choice выбирает номер'),
    ('Компактизация', 'вызов инструмента', 'два Noul: нужен ли вызов и нужен ли вывод'),
    ('Маршрутизация', 'признаки задачи', 'три независимых Choice в одном запросе'),
    ('Обход графа', 'кандидаты-рёбра', 'распределение как оценки гипотез'),
    ('Триаж ревью', 'файл × измерение', 'пять Noul за один round-trip'),
    ('Верификация', 'текст ответа', 'Noul об узком факте, не о качестве'),
]
for i, (title, inp, out) in enumerate(items):
    x = 64 + (i % 3) * 452
    y = 240 + (i // 3) * 268
    s.rect(x, y, 428, 232, stroke=C['line'])
    s.text(x + 24, y + 62, title, size=28, weight=700)
    s.text(x + 24, y + 108, 'вход: ' + inp, size=21, fill=C['muted'])
    s.line(x + 24, y + 134, x + 404, y + 134)
    s.lines(x + 24, y + 176, [out[:34], out[34:]] if len(out) > 34 else [out], size=21, dy=30)
s.save('07-applications.svg')

print('готово: 05-answer-layers.svg, 06-phrasing.svg, 07-applications.svg')
