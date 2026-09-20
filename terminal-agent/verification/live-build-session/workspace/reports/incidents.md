# Отчёт об инцидентах

Источник: examples/related\_failures\.jsonl

## Факты из журнала

Наблюдения из принятых записей журнала; достоверность источника отдельно не проверялась.

- Строк: 12; пустых: 0; битых: 2.
- Уникальных событий: 8; дублей: 2, из них конфликтующих: 1.
- Ошибок в периоде: 7; прочих событий в периоде: 1; вне периода: 0.

Время приведено к UTC. Границы периода включены. Окно связи: 120 с.
Период: без нижней границы — без верхней границы.

### Группы ошибок по сервису и причине

Причина здесь — текст диагностики из лога, а не доказанная первопричина.

- **api / database timeout**: 2; 2026-09-19T09:00:02Z — 2026-09-19T09:01:02Z. event_id: api\-001, api\-002.
- **database / connection pool exhausted**: 2; 2026-09-19T09:00:00Z — 2026-09-19T09:01:00Z. event_id: db\-001, db\-002.
- **telemetry / dns lookup failed**: 1; 2026-09-19T08:59:59Z — 2026-09-19T08:59:59Z. event_id: noise\-001.
- **web / checkout unavailable**: 2; 2026-09-19T09:00:04Z — 2026-09-19T09:01:04Z. event_id: web\-001, web\-002.

### Хронология принятых ошибок

- 2026-09-19T08:59:59Z — event_id: noise\-001; сервис: telemetry; ERROR; причина: DNS lookup failed; trace_id: monitor\-77; upstream_service: dns.
- 2026-09-19T09:00:00Z — event_id: db\-001; сервис: database; ERROR; причина: Connection pool exhausted; trace_id: checkout\-42; upstream_service: —.
- 2026-09-19T09:00:02Z — event_id: api\-001; сервис: api; ERROR; причина: Database timeout; trace_id: checkout\-42; upstream_service: database.
- 2026-09-19T09:00:04Z — event_id: web\-001; сервис: web; ERROR; причина: Checkout unavailable; trace_id: checkout\-42; upstream_service: api.
- 2026-09-19T09:01:00Z — event_id: db\-002; сервис: database; CRITICAL; причина: connection pool exhausted; trace_id: checkout\-43; upstream_service: —.
- 2026-09-19T09:01:02Z — event_id: api\-002; сервис: api; ERROR; причина: Database timeout; trace_id: checkout\-43; upstream_service: database.
- 2026-09-19T09:01:04Z — event_id: web\-002; сервис: web; ERROR; причина: Checkout unavailable; trace_id: checkout\-43; upstream_service: api.

## Гипотезы о причине

**Первопричина не доказана.**

Первопричина не доказана: диагностическая причина в логе и корреляция не устанавливают причинность.

### H001 — гипотеза

Сбой api \(database timeout\) мог способствовать сбою web \(checkout unavailable\)\.

event_id доказательств наблюдаемой связи: api\-001, web\-001, api\-002, web\-002

- api\-001 → web\-001; trace_id: checkout\-42; задержка по журналу: 2 с.
- api\-002 → web\-002; trace_id: checkout\-43; задержка по журналу: 2 с.

Совпали trace_id, заявленный upstream_service и временное окно; причинность не доказана.
Порядок основан на часах источников; рассинхронизация часов и общая внешняя причина не исключены.

Проверки:

- Проверить spans этой трассы и фактический вызов upstream-сервиса.
- Сопоставить метрики и журналы upstream-сервиса, проверить альтернативные причины.

### H002 — гипотеза

Сбой database \(connection pool exhausted\) мог способствовать сбою api \(database timeout\)\.

event_id доказательств наблюдаемой связи: db\-001, api\-001, db\-002, api\-002

- db\-001 → api\-001; trace_id: checkout\-42; задержка по журналу: 2 с.
- db\-002 → api\-002; trace_id: checkout\-43; задержка по журналу: 2 с.

Совпали trace_id, заявленный upstream_service и временное окно; причинность не доказана.
Порядок основан на часах источников; рассинхронизация часов и общая внешняя причина не исключены.

Проверки:

- Проверить spans этой трассы и фактический вызов upstream-сервиса.
- Сопоставить метрики и журналы upstream-сервиса, проверить альтернативные причины.

## Ошибки без достаточных данных для связи

event_id: noise\-001

Это не доказательство независимости. Близость по времени сама по себе не связывает события.

## Предупреждения чтения

- Строка 10: Expecting property name enclosed in double quotes: line 1 column 23 \(char 22\).
- Строка 11: timestamp должен содержать дату, время и часовой пояс \(Z или ±HH:MM\).
- Строка 12: конфликтующий дубль event\_id=api\-001; сохранена первая валидная запись.
