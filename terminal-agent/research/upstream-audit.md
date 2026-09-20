# Jev Terminal: исследование исходников Pi, PiJev, OpenCode и Crush

Дата исследования: 21 сентября 2026. Это исследование конкретных checkout, а не обещание функций из меняющегося README. Исходники изучались локально, upstream-программы не запускались; их тесты в рамках этого аудита не выполнялись. Проверки нашего агента описываются отдельно в `verification/`.

## Вывод для нашего продукта

Самое полезное заимствование — устройство работы, а не просто цветовая тема: одна лента разговора, одна обновляемая карточка на вызов инструмента, раскрываемый вывод, отдельные сохранённые события, удобный редактор и доступ к предыдущим сессиям. Пользователь должен видеть, что именно сделал агент, чем закончилась команда и где лежит результат. Граф и вероятности Jev помогают объяснить процесс, но не должны постоянно отбирать половину экрана у разговора.

Для этой версии разумно сохранить наш Python/Textual + Codex runtime и перенести подходящие механизмы. Полный переход на Pi/PiJev даст больше готовых возможностей, но одновременно заменит запуск модели, авторизацию, хранение сессий, tools и UI. Это отдельная миграция, а не установка темы. OpenCode ещё значительно шире: TUI, сервер, SDK, SQLite, плагины, провайдеры, контроль разрешений и рабочие пространства образуют общую систему.

Jev остаётся явно видимым слоем решений. Пользователь должен отличать «Jev выбрал исходники», «Codex выполнил команду», «harness запустил тест» и «Jev предложил завершение». Одна зелёная галочка не должна объединять эти разные факты.

## Что действительно исследовано

Зафиксированы версии:

- **Pi** — `f5c946480c575604c50d810adc88b11679d6aecb`, [репозиторий на этом commit](https://github.com/earendil-works/pi/tree/f5c946480c575604c50d810adc88b11679d6aecb).
- **PiJev** — `0b67ff916fb9c6cadd4d939b8a7a14976252efef`, [репозиторий на этом commit](https://github.com/tonyzdev/pijev/tree/0b67ff916fb9c6cadd4d939b8a7a14976252efef).
- **OpenCode** — `d870e22c70f27103016dcd479edcfebf86136d93`, [репозиторий на этом commit](https://github.com/anomalyco/opencode/tree/d870e22c70f27103016dcd479edcfebf86136d93).
- **Crush** — `afb55f03c5f510bebeb04197ee05fbe540384db8`, [репозиторий на этом commit](https://github.com/charmbracelet/crush/tree/afb55f03c5f510bebeb04197ee05fbe540384db8).

Инвентаризация через `git ls-files` и число строк в отслеживаемых `.ts/.tsx/.js/.mjs/.go/.py/.zig` дала: Pi — 1 537 файлов / 362 720 строк; PiJev — 115 / 8 740; OpenCode — 3 344 / 683 680; Crush — 670 / 157 185. Это исходники вместе с тестами и fixtures; число не является оценкой сложности production-кода. В сумме — 1 212 325 строк. Они не прочитаны все. Проверены релевантные сквозные пути: запуск, агентный цикл, события инструментов, сохранение истории, терминальный редактор, отображение tools, обработка ошибок и точки расширения. В остальных файлах использовались поиск символов и навигация по зависимостям.

PiJev особенно удобен для подробного изучения: весь его `src/` занимает 1 239 строк в десяти файлах. Большую часть самого агента он наследует из Pi. Его `package.json` закрепляет **Pi 0.85.1**, а исследованный checkout Pi содержит также новый harness с lanes и JSONL v4. Нельзя автоматически считать, что все новые API Pi из этого checkout доступны PiJev 0.1.0. [Зависимости PiJev](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/package.json).

## Pi: модель событий и хороший терминальный слой

### Как доходит запрос

`packages/coding-agent/src/main.ts` разбирает аргументы, выбирает session manager, создаёт services/runtime и передаёт runtime в `InteractiveMode`. Это важная граница: терминал не должен сам владеть вызовами модели. Наше разделение `JevApp` → `Session` уже соответствует этому принципу. [Точка запуска](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/main.ts#L566).

В классическом пути `AgentSession` подписывается на события agent-core, сохраняет сообщения и предоставляет подписку UI. В `agent-loop.ts` внутренний цикл выполняет tool calls, возвращает tool results в контекст и снова вызывает модель. Внешний цикл подхватывает follow-up после естественного завершения. Steering и follow-up имеют разные моменты доставки. Обрезанные лимитом токенов tool arguments не исполняются как полноценные вызовы: цикл создаёт ошибки для этих tools. [Агентный цикл](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/agent/src/agent-loop.ts#L161).

### Почему логи читаются

В `AgentEvent` есть отдельные `tool_execution_start`, `tool_execution_update`, `tool_execution_end`; во всех сохраняется **toolCallId**. `InteractiveMode.pendingTools` — map по этому ID. Start создаёт карточку, update меняет её содержимое, end выставляет результат и убирает вызов из списка незавершённых. Несколько обновлений одного процесса не превращаются в несколько независимых команд. [Типы событий](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/agent/src/types.ts#L458), [обработка в терминале](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/interactive-mode.ts#L3412).

`ToolExecutionComponent` разделяет аргументы и результат, умеет принимать частичный результат, отображать ошибку, показывать компактный preview и раскрывать остальное. Пользователь видит, что скрыто, и как раскрыть вывод. Для зарегистрированного инструмента можно определить свои `renderCall` и `renderResult`; есть общий fallback. [Карточка инструмента](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/components/tool-execution.ts#L156).

В нашем исходном `runtime.py` `item.id` из Codex JSONL терялся. Это главное структурное препятствие качественному UI. Нужен ID, уникальный в пределах хода и worker-attempt, а для проверок — собственный ID harness. Нельзя связывать карточки по тексту shell-команды: одна и та же команда законно выполняется повторно.

### Редактор и история

Pi имеет отдельный Editor с Unicode/grapheme-aware навигацией, soft wrap, undo, историей, autocomplete и обработкой bracketed paste. `CustomEditor` добавляет клавиши приложения; Escape сначала закрывает autocomplete, и только затем может прервать агент. Рабочий статус может находиться в верхней границе редактора вместо отдельной большой панели. [Editor](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/tui/src/components/editor.ts), [CustomEditor](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/modes/interactive/components/custom-editor.ts).

Большие вставки Pi умеет сворачивать в маркеры. **У нас это не должно стать поведением по умолчанию:** пользователь уже попросил видеть сообщение целиком. Полезны сохранение оригинала, корректная вставка переносов, прокрутка, раскрытие редактора и история; скрытие длинного запроса за `[paste #...]` противоречит текущему запросу.

Session manager хранит append-only entries с `id`/`parentId`, изменения модели, compaction и branch summaries. CustomEntry может сохраняться, не попадая в LLM-контекст; CustomMessageEntry отдельно управляет модельным контекстом и отображением. Это три разных слоя: durable history, context, presentation. [Формат сессии](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/packages/coding-agent/src/core/session-manager.ts#L40).

Нашему агенту сейчас достаточно линейного JSONL и resume. Развилки, compaction и полноценное продолжение нативной model session нельзя обещать только потому, что мы сохраняем события. Наш Codex стартует `--ephemeral`; следующий ход получает текстовый контекст из сохранённой истории и файлы workspace. Это ограниченное продолжение, а не восстановление всех внутренних сообщений Codex.

### Расширение

Pi даёт event hooks, custom tools, slash commands и UI renderers. PiJev пользуется именно этими границами. Переносить всю систему динамических plugins в наш учебный агент необязательно: достаточно явных Python-границ для подготовки context, решения Jev, выполнения worker, проверки и projection событий. Если в будущем сменить runtime, это позволит заменить adapter без переписывания терминала.

## PiJev: наиболее полезный источник функций Jev

### Реальная архитектура

`cli.ts` загружает конфигурацию и вызывает Pi `main` с `extensionFactories: [{name: "pijev", factory: ...}]`. Функция `createPijevExtension` подключается к session start/shutdown, before_agent_start, context и tool_result; регистрирует `/pijev` и `pijev_search`. Генеративная модель Pi остаётся исполнителем. [CLI](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/cli.ts#L94), [extension](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/extension.ts#L14).

### Поиск исходников

Поиск сначала создаёт реальные кандидаты, а уже потом передаёт их Jev. Literal search вызывает `rg --fixed-strings --json`, возвращает путь, номера строк и excerpt. Discovery перечисляет доступные файлы, выполняет ограниченное чтение, лексически ранжирует файлы через BM25 и строит shortlist. Jev не придумывает пути и код — задаётся Noul-вопрос о релевантности каждого существующего кандидата. Результат сортируется по возвращённому значению. [Literal search](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/search.ts#L25), [discovery](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/discovery.ts#L240), [rankCode](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/decisions.ts#L71).

Есть точные ограничения: discovery перечисляет до 20 000 файлов, читает до 48 MiB суммарно, до 256 KiB на файл и не дольше 8 секунд этапа чтения; shortlist по умолчанию — 100 файлов. Excerpt ограничен 1 800 байтами, outline — 1 200. Это не полный обзор репозитория, и upstream явно маркирует неполный охват.

Ранжирование разбивается на запросы до внутреннего лимита payload. При ошибке одного batch частичная «умная сортировка» отбрасывается целиком: возвращается исходный список. Такой подход предотвращает ситуацию, когда оценённая половина кандидатов получает несправедливое преимущество над неоценённой.

Автоматический source briefing показывает максимум три разных файла. Для уверенного top candidate допускается полный файл в пределах 50 KiB. Подсказка привязана к конкретному user-message ID и вставляется рядом с этим запросом, а не повторяется после каждого инструмента. Комментарии и исходники явно помечены как данные, а не инструкции.

**Адаптация для русского обязательна.** В исследованном `discovery.ts` tokenizer понимает латиницу и Han, но не кириллицу. Русский запрос без английских идентификаторов даёт бедный или пустой набор lexical terms; Jev не сможет спасти файл, который не попал в shortlist. Для нашего варианта нужны Unicode-токены и проверка русского запроса. Простое совпадение слов, даже с хорошей оценкой Jev, не доказывает, что выбран единственный правильный файл.

### Skills и диагностика ошибок

Skill selection двухэтапный: короткие описания дают shortlist, затем читаются ограниченные инструкции top candidates и проверяется реальная полезность. Явно выбранный пользователем skill имеет приоритет; весь roster остаётся доступен. Это хороший общий принцип, но нам не нужен ложный `/skills`, пока executor действительно не умеет получать и применять выбранные инструкции.

Failure triage запускается только после error tool result, максимум два раза за ход, и не анализирует собственный `pijev_search`. Jev выбирает одну из категорий code/environment/dependency/network/permission/unknown. Возвращается заранее написанная осторожная подсказка, только если confidence и probability проходят пороги. Диагноз маркируется как предположение, не подтверждённая root cause. [DecisionEngine](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/decisions.ts#L105), [tool_result hook](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/extension.ts#L167).

В нашем Codex subprocess нельзя просто вставить extension hook Pi и вмешаться между любыми двумя внутренними tool calls. Сейчас разумная точка интеграции — после завершения worker-attempt или harness-check, перед следующей попыткой. Визуально нельзя выдавать такую диагностику за управление каждой shell-командой в реальном времени.

### Режимы, отмена и транспорт

PiJev поддерживает `assist`, `observe`, `off`. Observe делает запросы и записывает метаданные, но не применяет рекомендации; off не вызывает Jev. Это даёт полезную базу сравнения, однако одного наблюдения в observe недостаточно, чтобы доказать выигрыш в качестве или стоимости. Нужны одинаковые задачи и измеримые исходы.

JevClient имеет bounded request/response, таймаут, общий AbortSignal, валидацию типов и вероятностей, cache по SHA-256 полного body на пять минут, максимум 128 записей и cooldown после серии сбоев. По умолчанию запрос ограничен 1 800 мс, payload — 90 KB, response — 1 MB. Неудача optional advisory возвращает явный fallback. [JevClient](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/jev.ts#L67).

Это не аргумент ослаблять наш обязательный Jev route/review: разные границы отказа. Если необязательный source ranking недоступен, можно продолжить с lexical shortlist и показать fallback. Если обязательный decision gate не дал валидного результата, нельзя рисовать успешный ответ Jev.

DecisionJournal пишет отдельный allowlist метаданных: mode, kind, status, latency, token usage, sessionId и userMessageId. Не пишет source, prompts и ответы. У нас задача статьи требует подробных свидетельств, поэтому raw local evidence сохраняется отдельно, а компактный UI и экспорт должны выбирать минимально необходимое. Токены cache hit upstream не считает повторно израсходованными. [Журнал решений](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/src/telemetry.ts#L20).

## OpenCode: разделение разговора и подробностей

В изученной версии terminal frontend находится в `packages/tui`, а основная сессия — в `packages/opencode/src/session`. Часто встречающийся старый путь `packages/opencode/src/cli/cmd/tui` здесь уже неверен.

`prompt.ts` собирает user message и запускает session loop; `processor.ts` преобразует stream events в сохранённые message parts. Tool part имеет `callID` и состояния pending → running → completed/error. Start фиксирует время; result записывает output, title, metadata и attachments; abort закрывает незавершённые вызовы. UI получает данные через SDK/sync. Поэтому перерисовка экрана не равна исполнению команды. [Session loop](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/session/prompt.ts#L1081), [processor](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/opencode/src/session/processor.ts#L236).

Повтор одинаковых tool calls обнаруживается отдельно от модели. Есть compaction, восстановление прерванных tools, retry status и хранение структуры сессии в SQLite. Это нельзя заменить одной надписью «умная память». Нашему агенту сейчас ближе явные лимиты попыток, no-progress detection и линейное сохранение результата.

Terminal session view отдельно управляет sidebar, timestamps, tool details, generic output и прокруткой по сообщениям. Generic tool output по умолчанию скрыт; пользователь может раскрыть его. Ограничение preview учитывает одновременно строки и символы. Нам подходит этот принцип, но важная ошибка и exit code должны оставаться видимыми без раскрытия. [Session UI](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/routes/session/index.tsx#L256), [ограничение вывода](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/util/collapse-tool-output.ts).

Prompt history и stash — отдельные JSONL, по 50 последних записей. Парсер пропускает повреждённые строки, повтор предыдущего prompt не дублируется, history navigation не должна затирать отличающийся текущий черновик. Stash сохраняет также parts и timestamp. В submit есть защита от двойной отправки: две конкурентные отправки до очистки редактора иначе способны создать лишнюю пустую сессию. [History](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/prompt/history.tsx), [stash](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/prompt/stash.tsx), [submit guard](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/tui/src/component/prompt/index.tsx#L930).

OpenCode представляет файлы, вставки и изображения как prompt parts с привязкой к диапазонам редактора. Большая вставка может сворачиваться в `[Pasted ~N lines]`. Как и у Pi, у нас это полезный механизм сохранения данных, но неподходящий default отображения. Автоматическое чтение пути из буфера тоже не требуется: явная команда добавления файла понятнее для нашего читателя.

Session picker имеет поиск, показывает выбранную сессию и работает с metadata, а не читает все большие raw logs ради первого экрана. Для нас полезны `/sessions`, выбор по заголовку/дате и локальный export отчёта. Resume должен загружать выбранный workspace и историю, а не незаметно создавать новую задачу.

Plugin API OpenCode содержит server hooks, custom tools и workspace adapters. Его копирование отдельно от сервера/SDK не даст работающей расширяемости. В этой версии это референс интерфейсов, а не подключаемый модуль нашего Python runtime. [Plugin types](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/packages/plugin/src/index.ts).

## Crush: важные детали поведения

Crush использует Go, Bubble Tea, Lip Gloss, Fantasy и SQLite. `internal/agent/agent.go` связывает события генерации с message service: tool-input создаёт ToolCall, завершённый вызов обновляет input, ToolResult сохраняется отдельно и связан по ToolCallID. При отмене tool results сохраняются через живой parent context, чтобы отменённый generation context не уничтожил свидетельства уже совершённых действий. [Обработчики runtime](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/internal/agent/agent.go#L920).

Значимые детали, которые стоит воспроизвести собственной реализацией:

- Команда и её stdout — разные визуальные элементы. В `bash.go` текст самой shell-команды остаётся видимым, а output может быть свёрнут. Проверки этого поведения находятся рядом в `bash_test.go`.
- FinishReason различает normal end, token limit, cancellation, error и provider refusal. Пустой ответ после отказа не выглядит как успешная тишина. [Message types](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/internal/message/content.go#L31).
- Retry очищает partial streamed content перед повтором, чтобы две попытки не склеились в один будто бы связный ответ.
- Session хранит `EstimatedUsage`; интерфейс может показывать, что расход приблизительный. Наше `usage_complete=false` также должно быть видимо.
- Session picker имеет нормальный список, поиск/фильтрацию, переименование и отдельные режимы действий. [Session dialog](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/internal/ui/dialog/sessions.go).
- Loop detection смотрит на повторяющиеся пары tool input/result, а не только на название команды. Повтор `pytest` после реального исправления не равен зацикливанию. [Loop detection](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/internal/agent/loop_detection.go).

Исходники Crush в продукт не копируются: причины описаны ниже. Наличие отдельного открытого компонента экосистемы Charm не означает такую же лицензию у всего Crush.

## Приоритет переноса в наш агент

**Основа удобства и проверяемости.** Лента диалога; компактные tool rows с identity/lifecycle; раскрытие подробностей; видимые ошибки; многострочный редактор; исходный JSONL отдельно; компактный status; граф только по действительно пришедшим событиям. UI должен одинаково проецировать live events и сохранённую историю, не вызывая модели при загрузке.

**Функции ежедневной работы.** Session picker/resume, история отправленных запросов с сохранением текущего черновика, command palette, явно добавляемый file context, список изменённых файлов, export Markdown с путями к evidence. Эти функции помогают пользователю закончить работу и вернуться к ней, а не только посмотреть красивый прогон.

**Более содержательное участие Jev.** Ограниченный source shortlist из реальных файлов и Noul ranking; ограниченная диагностика конкретно упавших проверок; прозрачные purpose/model/duration/fallback. Эти этапы должны передавать полезные данные следующему worker-attempt, иначе мы получим только декоративные вызовы модели.

**Отдельная архитектурная работа.** Прямая смена провайдера, native model-session resume, compaction, branching, undo рабочих файлов, MCP, параллельные subagents, фоновые jobs и динамические plugins требуют новых контрактов. Кнопки без работающей реализации здесь вреднее отсутствия кнопок. Snapshot с SHA-256 даёт доказательство изменения, но не даёт восстановление исходного содержимого; его нельзя назвать undo.

## Границы корректного переноса

Лицензии проверены в локальных checkout. Pi — MIT, copyright Mario Zechner; PiJev — MIT, copyright PiJev contributors; OpenCode — MIT, copyright opencode. При переносе существенного исходного кода необходимо сохранить соответствующий copyright/license notice. В этой исследовательской записке описываются механизмы; production-исходники upstream в неё не скопированы. [Pi LICENSE](https://github.com/earendil-works/pi/blob/f5c946480c575604c50d810adc88b11679d6aecb/LICENSE), [PiJev LICENSE](https://github.com/tonyzdev/pijev/blob/0b67ff916fb9c6cadd4d939b8a7a14976252efef/LICENSE), [OpenCode LICENSE](https://github.com/anomalyco/opencode/blob/d870e22c70f27103016dcd479edcfebf86136d93/LICENSE).

Текущий Crush содержит **FSL-1.1-MIT** с ограничением Competing Use и переходом конкретной версии на MIT спустя два года. Отдельный исторический MIT notice в том же файле не делает весь текущий checkout MIT. Для этой работы выбран конкретный практический подход: исходный код Crush не переносится; используются наблюдения о поведении интерфейса. [Crush LICENSE](https://github.com/charmbracelet/crush/blob/afb55f03c5f510bebeb04197ee05fbe540384db8/LICENSE.md).

Отдельно от лицензий нужна честность поведения. Confidence Jev не означает вероятность отсутствия ошибок во всём приложении. Model-generated tests не превращаются в независимую приёмку. Скрытие reasoning в нашем runtime сохраняется: экран показывает инструменты, фактические проверки и явно сформированные объяснения результата, а не заявляет доступ к скрытому мышлению модели.

## Какие проверки нужны перенесённым механизмам

Это критерии качества реализации, а не отчёт об уже пройденных тестах:

1. Start/update/end одного tool ID дают одну карточку; повтор команды с другим ID остаётся отдельным вызовом; одинаковые raw IDs в разных попытках не сливаются.
2. Отмена/ошибка закрывает running state, сохраняет уже полученный output и не помечает tool выполненным успешно.
3. Сохранённая сессия открывается без API-вызовов; события старого формата без ID продолжают читаться.
4. Вставка русского многострочного запроса не отправляет его автоматически, не меняет переносы и не скрывает текст за единственным placeholder.
5. История и выбор сессии не уничтожают непустой черновик; двойное нажатие отправки не запускает два worker.
6. Source context ограничен по файлам/байтам, не следует symlink за пределы workspace, исключает credentials и допускает кириллицу в запросе; старый excerpt не выдаётся за актуальный после изменения файла.
7. Ошибка optional Jev ranking оставляет отмеченный lexical fallback; ошибка обязательного decision gate не становится фальшивым результатом Jev.
8. Export содержит реальные статусы и пути к свидетельствам; отображаемые аргументы и output очищены от terminal control sequences и явных секретов.
9. Узкий экран 80×24 сохраняет доступ к разговору, отправке и ошибкам. Полный экран не зависит от открытой debug-панели.

Исследование показывает, какие части действительно можно перенести с пользой. Какие из них уже реализованы в нашем checkout, определяют текущий код, README и результаты тестирования; упоминание функции upstream само по себе не является заявлением о её наличии у нас.
