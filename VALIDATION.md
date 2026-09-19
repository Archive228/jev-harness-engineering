# Результаты проверок · 19 сентября 2026

## Автоматические проверки

**67 тестов проходят** на macOS / Python 3.9.6. Точный вывод: [test log](./verification/python-3.9.6-tests.txt), метаданные: [local-tests.json](./verification/local-tests.json).

```bash
cd jev-harness-lab
python3 -B -m unittest discover -s tests -v
```

Проверяются не только успешные сценарии. Регрессии покрывают `sys.exit(0)` и аварийный выход приложения до завершения проверки; изменение кода или контракта во время проверки; устаревшие и дублирующиеся записи; неполный acceptance report; неизвестные варианты Choice; повреждённый ответ API; ошибки инструментов; таймауты и лимиты; дочерние процессы после завершения worker; отсутствие утечки credentials в проверки и независимый oracle; остановку replay при первом расхождении.

Тесты клиента Jev используют контролируемые ответы транспорта и проверяют запрос, валидацию ответа, ошибки и deadline. Синтетические ответы не выдаются за предсказания сервиса.

## Настоящий Codex worker

Использована установленная CLI `0.155.0-alpha.9`, авторизация ChatGPT и текущая настроенная модель без переопределения. Три варианта ошибки и их хеши сохранены до запуска; по одному прогону каждого. Selector — `fixed`; реальных запросов Jev в этом опыте **0**.

- `ui-title-only`: complete, одно исправление, пять проверок, независимая приёмка PASS; 15,17 с.
- `backend-title-only`: complete, одно исправление, пять проверок, независимая приёмка PASS; 17,02 с.
- `both-title-only`: complete, одно исправление, пять проверок, независимая приёмка PASS; 20,43 с.

Время включает весь прогон и независимый oracle. Все три worker действительно меняли `app.py`. Итоговая проверка исполнялась после остановки в отдельном процессе с очищенным окружением и проверяла четыре дополнительных запроса. Ложных complete в этих трёх случаях нет. Это небольшой опыт на подготовленных дефектах, а не оценка общей надёжности coding agent.

Полные исходники, ответы worker, usage и журналы: [evaluation.md](./verification/codex-worker-2026-09-19/evaluation.md), [evaluation.json](./verification/codex-worker-2026-09-19/evaluation.json), [manifest.json](./verification/codex-worker-2026-09-19/manifest.json).

```bash
python3 adapters/codex_cli.py --configure
python3 worker_eval.py --out runs/my-worker-evaluation
```

## Offline-матрица и примеры

Девять запусков `evaluate.py`: три подготовленных случая × fixed/all/jev. Шесть complete, три ожидаемых остановки без прогресса. Все девять получили независимую финальную проверку; ложных complete нет. Fixed/all не вызывают judge; в варианте demo/jev ответы judge подготовлены. Эта матрица проверяет программную механику, а не преимущество модели.

Отдельно пересозданы inspect, evidence, next-check и три loop-примера с актуальным контрактом проверки. Replay `runs/example` совпадает с исходной политикой; изменение бюджета проверено тестом на расхождение.

## Прогон TypeSafe/Jev

Зафиксирован набор из **18 состояний / 28 решений**: десять RU/EN обращений и восемь диагностических случаев. Gold скрыт от модели; пороги не подгоняются после ответов. Runner сохраняет запросы и полные provider responses, метаданные и токены, отдельно считает accuracy, coverage, отказы по неуверенности и `none_suitable`.

Для выполнения нужен `TYPESAFE_API_KEY`. На момент этой записи доступ TypeSafe ещё не предоставлен; живые оценки Jev здесь не заявлены. Это единственный незавершённый внешний эксперимент. Код runner и его обработка ошибок проверены тестами, но они не заменяют запрос к сервису.

```bash
python3 live_eval.py --out runs/my-jev-evaluation
python3 run.py loop --mode live --selector jev --case missing-evidence --worker-config worker-config-codex.json --policy policy-codex.json
```

## Репозиторий, CI и статья

Репозиторий: [Archive228/jev-harness-engineering](https://github.com/Archive228/jev-harness-engineering). Workflow выполняет unit/subprocess tests и offline-матрицу на Python 3.9, 3.12 и 3.13. Состояние конкретного коммита видно в [GitHub Actions](https://github.com/Archive228/jev-harness-engineering/actions).

HTML воспроизводится из Markdown командами `npm ci --ignore-scripts` и `npm run build:article`; Node >=20, зависимость `marked` зафиксирована в lockfile. Четыре SVG/PNG проверены визуально. HTML проверялся на ширине 1440 и 390 px: иллюстрации загружаются, горизонтального переполнения нет.

API-ключи, локальные конфиги с абсолютными путями и произвольные новые runs исключены из Git. В curated-следах абсолютный путь автора заменён на `<workspace>`; сохранённые фактические ответы и хеши исходников не изменены.
