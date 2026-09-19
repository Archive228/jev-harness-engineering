# Jev + Harness Engineering

[![Test harness](https://github.com/Archive228/jev-harness-engineering/actions/workflows/tests.yml/badge.svg)](https://github.com/Archive228/jev-harness-engineering/actions/workflows/tests.yml)

Полная статья и небольшая лаборатория: Choice, Score, Noul → отчёт по требованиям → выбор диагностики → ограниченный цикл исправления кода.

**Проверено:** 67 автоматических тестов; три настоящих исправления через Codex CLI с независимой итоговой приёмкой; девять offline-прогонов трёх политик. Результаты и исходные записи находятся в [VALIDATION.md](./VALIDATION.md). Это проверка механики на маленьком приложении, без обещаний универсальной надёжности.

## Читать

- [Статья в Markdown](./jev-engineering.md).
- [HTML для локального чтения](./jev-engineering.html): оглавление, копирование кода, увеличение схем.
- [Настоящий Codex: результаты трёх опытов](./verification/codex-worker-2026-09-19/evaluation.md).
- [Схемы в SVG/PNG](./assets/README.md).
- [Описание лаборатории](./jev-harness-lab/README.md).

## Запустить без ключей

Python 3.9+, macOS/Linux; внешние Python-пакеты не нужны.

```bash
git clone https://github.com/Archive228/jev-harness-engineering.git
cd jev-harness-engineering/jev-harness-lab
python3 run.py loop --mode demo --case missing-evidence
python3 -m unittest discover -s tests -v
```

В demo исполняется настоящий код приложения и проверки. Ответы judge и изменение worker подготовлены заранее и явно помечены.

## Настоящий coding agent

Используется авторизованная Codex CLI. Настройте доступ и сгенерируйте пути текущей установки:

```bash
codex login status
python3 adapters/codex_cli.py --configure
python3 run.py loop --mode live --selector fixed --case missing-evidence --worker-config worker-config-codex.json --policy policy-codex.json
python3 worker_eval.py --out runs/my-worker-evaluation
```

`worker_eval.py` выполняет три живые задачи и расходует лимит аккаунта Codex. Параметр `fixed` не вызывает Jev: это отдельная проверка worker и harness. [Настройка адаптера](./jev-harness-lab/codex-worker-setup.md).

## Jev

Установите `TYPESAFE_API_KEY` в окружении, затем из каталога лаборатории:

```bash
python3 run.py inspect --mode live --case export-ticket
python3 live_eval.py --out runs/my-jev-evaluation
python3 run.py loop --mode live --selector jev --case missing-evidence --worker-config worker-config-codex.json --policy policy-codex.json
```

Размеченный набор и пороги фиксируются до получения ответов; gold не передаётся модели. [Методика 18 случаев](./jev-harness-lab/live-eval-method.md). Текущий статус доступа к сервису отражён в протоколе проверки. Числа из demo не считаются результатами Jev.

## Собрать HTML

Для редактирования самой статьи: Node >=20 и зафиксированный npm lockfile.

```bash
npm ci --ignore-scripts
npm run build:article
```

Python-лаборатории Node не нужен. API-ключи и локальные конфиги с абсолютными путями исключены из Git. После переноса каталога повторите `--configure`.
