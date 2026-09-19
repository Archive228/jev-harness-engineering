#!/usr/bin/env python3
"""Standalone Russian-language example. Requires TYPESAFE_API_KEY.
Live accuracy has not been evaluated; questions match the article.
"""
category_question = {
    "type": "choice",
    "instructions": "К какой категории относится основная проблема?",
    "criteria": {
        "export": "Создание или скачивание экспортируемого файла",
        "account": "Вход в аккаунт и доступ к нему",
        "payment": "Списания, счета и платежи",
        "other": "Ни одна из перечисленных категорий не подходит",
    },
}


impact_question = {
    "type": "score",
    "instructions": "Как проблема влияет на выполнение задачи?",
    "criteria": [
        "Косметический дефект; задача выполняется обычным способом",
        "Функция нарушена, но указан рабочий обходной путь",
        "Задача заблокирована; рабочего обходного пути нет",
    ],
}


workaround_question = {
    "type": "noul",
    "instructions": "Указан ли в обращении рабочий обход проблемы?",
    "criteria": {
        "true": "Автор прямо сообщает, что выполняет ту же задачу другим способом",
        "false": "Рабочий обход не указан; есть лишь предположение или его нет совсем",
    },
}


questions = {
    "category": category_question,
    "impact": impact_question,
    "has_workaround": workaround_question,
}


import json
import os
from urllib.request import Request, urlopen

ticket = (
    "В Safari экспорт PDF завершается ошибкой. "
    "В Chrome тот же документ экспортируется. "
    "Сейчас пользуюсь Chrome, но хочу вернуть экспорт в Safari."
)
payload = {
    "model": "jev-1.13.0",
    "state": ticket,
    "questions": questions,
}
request = Request(
    "https://api.typesafe.ai/v1/systemone",
    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    headers={
        "Authorization": "Bearer " + os.environ["TYPESAFE_API_KEY"],
        "Content-Type": "application/json",
    },
    method="POST",
)
with urlopen(request, timeout=30) as response:
    result = json.load(response)

answers = result["answers"]
print(answers["category"]["choice"])
print(answers["impact"]["score"])
print(answers["has_workaround"]["noul"])
