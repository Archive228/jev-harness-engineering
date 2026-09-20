# Jev + Harness Engineering

[![Test harness](https://github.com/Archive228/jev-harness-engineering/actions/workflows/tests.yml/badge.svg)](https://github.com/Archive228/jev-harness-engineering/actions/workflows/tests.yml)

Полная статья и лаборатория, в которой можно увидеть весь путь: Choice, Score и Noul → проверка требований → выбор диагностики → исправление кода → повторная приёмка.

**Начни с [маршрута на 10 минут](./START-HERE.md).** На выходе будут исправленная копия маленького приложения, отчёт по требованиям и журнал решений. Первый запуск работает без ключей; затем те же инструменты можно подключить к настоящим Jev и Codex.

## Что уже проверено

- **83 автоматических теста проходят локально.** [Полный вывод](./verification/terminal/unit-tests-83.txt).
- **Два живых набора Jev:** по 18 запросов и 28 правильных решений в каждом. Первый запрос статьи отдельно выполнен с русскими формулировками. Это небольшие авторские наборы, а не оценка надёжности на любых данных.
- **Связка Jev + Codex:** два дефекта исправлены, третий прогон остановлен из-за confidence 0.52 при пороге 0.60. После явного переключения копии этого состояния на все диагностики Codex исправил и третий дефект. Исходная остановка сохранена.
- **Девять offline-сценариев:** шесть завершений, три ожидаемых остановки; ложных `complete` нет.

Подробности и границы каждого опыта: [VALIDATION.md](./VALIDATION.md). Скриншоты, терминальные протоколы и ссылки на исходные JSON: [галерея доказательств](./verification/evidence-gallery.html). Прежний опыт от 19 сентября с `fixed` и без Jev сохранён отдельно: [три запуска Codex](./verification/codex-worker-2026-09-19/evaluation.md).

## Читать и запускать

- [Статья в Markdown](./jev-engineering.md) и [готовый HTML](./jev-engineering.html).
- [Быстрый маршрут читателя](./START-HERE.md).
- [Описание лаборатории и её команд](./jev-harness-lab/README.md).
- [Методика живых проверок Jev](./jev-harness-lab/live-eval-method.md).
- [Схемы в SVG/PNG](./assets/README.md).

Нужны Python 3.9+ и macOS/Linux. Внешние Python-пакеты не нужны. Репозиторий пока приватный: без GitHub-доступа распакуй переданный с материалом архив статьи и открой папку `jev-harness-lab`. Если доступ есть:

```bash
git clone https://github.com/Archive228/jev-harness-engineering.git
cd jev-harness-engineering/jev-harness-lab
```

Из папки `jev-harness-lab`:

```bash
python3 run.py loop --mode demo --case missing-evidence --out runs/my-first-loop
python3 -B -m unittest discover -s tests -v
```

Ожидается `complete`: пять проверок и одно исправление. В demo исполняются настоящий код и тесты, а ответы judge и изменение worker подготовлены заранее. Для повторного запуска выбери новый `--out`: существующие результаты не перезаписываются.

## Подключить настоящий Jev и Codex

Передай ключ TypeSafe через переменную окружения `TYPESAFE_API_KEY`. Авторизуй Codex CLI и сгенерируй конфиг для текущих локальных путей:

```bash
codex login status
python3 adapters/codex_cli.py --configure
python3 run.py inspect --mode live --case export-ticket
python3 live_eval.py --out runs/my-jev-primary
python3 live_eval.py --cases fixtures/live-eval-challenge-cases.json --out runs/my-jev-challenge
python3 worker_eval.py --selector jev --out runs/my-jev-codex
```

Первые две оценки делают по 18 запросов TypeSafe. `worker_eval.py --selector jev` запускает три задачи с настоящими Jev и Codex и расходует их лимиты; Codex вызывается только если политика разрешила исправление. Результатом может быть обоснованная остановка. [Настройка адаптера](./jev-harness-lab/codex-worker-setup.md).

Для отдельной проверки Codex без Jev:

```bash
python3 worker_eval.py --selector fixed --out runs/my-codex-only
```

Noul в этой лаборатории лишь подписывает область действия теста. Его API-сбой сохраняется в отчёте и не отменяет детерминированную приёмку. Ошибка Choice-router останавливает цикл. Токены считаются по полученным счётчикам; `usage_complete` показывает, полны ли данные. Нулевые известные счётчики при ошибке не означают бесплатный запрос.

## Собрать HTML и проверить CI

Для редактирования статьи нужны Node >=20 и npm lockfile:

```bash
npm ci --ignore-scripts
npm run build:article
```

Python-лаборатории Node не нужен. Workflow настроен на Python 3.9 / 3.12 / 3.13 / 3.14 и отдельную проверку сборки HTML. Результат для конкретного коммита смотри в [GitHub Actions](https://github.com/Archive228/jev-harness-engineering/actions); локальные 83 теста и прежний зелёный CI не заменяют статус новой конфигурации.

API-ключи и локальные конфиги с абсолютными путями исключены из Git. После переноса каталога повтори `--configure`.

## Интерактивный агент в терминале

Готовый чат со свободным вводом, реальными действиями Codex и решениями Jev: [запуск и первый запрос](./terminal-agent/README.md). Команда `terminal-agent/jev` открывает пустой чат; работа начинается после Ctrl+D или кнопки «Отправить». Enter добавляет строку, F4 разворачивает редактор сообщения. История, файлы и протоколы сохраняются между сообщениями.
