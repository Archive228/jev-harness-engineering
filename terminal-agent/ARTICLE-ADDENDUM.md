## 13. Putting it all together in a terminal chat

Each of the three builds showed one piece on its own: what is confirmed, which observation to take next, and when to stop repairing. Now you can use them through an ordinary conversation. The `terminal-agent` directory holds a separate application: you write a task, the worker works with the files, and the terminal shows what is happening as it runs.

Start it from the `terminal-agent` directory:

```bash
./setup.sh
./jev
```

The first command creates a virtual environment and installs the interface dependencies. You need Python 3.9+, macOS or Linux, the Codex CLI installed and signed in, and a TypeSafe key in `TYPESAFE_API_KEY`. The command `./jev --doctor` checks that the environment is ready without calling any models. The details of setting up the key are in the `README.md` next to the application.

An empty chat opens. The agent waits for your message; no task is sent automatically at start-up. For example, this is the request that was sent in the recorded run, typed into the editor and sent with Enter or the **Discuss** button (that button reads **Send ↵** when you start with `--direct`):

> Создай CLI-анализатор инцидентов на Python без внешних библиотек: он читает JSONL, группирует ошибки по сервису и причине, убирает дубли event_id, правильно сравнивает часовые пояса и пропускает битые строки с предупреждением. Добавь пример связанных сбоев и ложный след, сохраняй JSON- и Markdown-отчёт с event_id, отделяй гипотезу о причине от доказанных фактов. Напиши и запусти unittest-тесты, выполни CLI на примере. В конце дай команду запуска. Реально создай файлы в текущей папке.

(In English: build a CLI incident analyser in Python with no external libraries: it reads JSONL, groups errors by service and by cause, drops duplicate event_id values, compares time zones correctly and skips broken lines with a warning. Add an example of related failures and a false trail, save a JSON and a Markdown report with event_id, and keep the hypothesis about the cause separate from the proven facts. Write and run unittest tests, and run the CLI on the example. At the end give the command to run it. Actually create the files in the current folder.) This run was done in Russian, so the recorded request in `verification/live-build-session/session.json`, the workspace it produced and the recorded terminal are all in Russian; the interface has since been translated, so the status and button names quoted here are the English ones the application shows now.

That is already a multi-file task: a parser, data processing, a command-line interface, a report and tests. You can open and run its result yourself. The text does not select a pre-recorded scenario: the worker receives exactly your request.

### Who is working right now

A plain `./jev` starts in the guided mode, so the first thing that happens is not a route but a discussion: one to three clarifying questions, a review screen for your answers, and a plan you accept with **Start work**, which runs exactly the version you reviewed. Only then does **Jev** answer a Choice: whether this needs the file-editing mode, project research or a conversational answer. **Codex** reads the material, writes code, runs commands and formulates the answer. **Harness** runs the checks, saves the results and limits how far the loop may continue. After an attempt Jev proposes completion, a repair or a clarification, and separately judges through Noul how well the work matches the request.

The terminal shows the chain of stages:

```text
Your request → questions → plan → Jev route → Codex → Checks → Jev review → Result
                                                ↑                  │
                                                └───── repair ─────┘
```

Nodes change state on actual events. The conversation shows the commands and their output; the panel on the right shows the Jev options with their probabilities, the checks and the changed files. Counters show the calls and the tokens for Jev and Codex separately. If a second attempt has started, that is a new call to the worker. The graph explains the sequence of actions; it does not depict the model's hidden reasoning.

### What is left after the answer

Files are created in the workspace, whose path is shown in the header. The session is saved next to it:

```text
.sessions/<id>/
  workspace/        the created project
  session.json      the conversation history
  events.jsonl      the observed events
  turn-001/         the request, the model answers, the checks and result.json
  screenshots/      screens saved with Ctrl+S
```

The status "Result prepared" means the worker has finished its work; the checks that ran are listed separately. Its own tests do not become independent acceptance. "Contract checks passed" refers only to the contract registered in advance and to the current version of the files. A failing check blocks acceptance regardless of Jev's answer.

Now write: **"Add a filter by service, keep the previous report format and check that filtering does not break the deduplication"**. The next turn receives the history and works in the same folder. You can return to it after closing the terminal with this command:

```bash
./jev --resume last
```

For your own project use `./jev --project /absolute/path/to/project`. For a separate exercise with a ready-made external contract, use `./jev --mission loglab`: the command creates a copy of the broken analyser, and you send the task yourself. **F2** only inserts an example into the multi-line field. **Enter** sends the whole text, **Ctrl+J** adds a line (Shift+Enter too, if the terminal passes it through), **Ctrl+D** is an additional way to send, **F4** expands the editor. **F3** opens the log, **Ctrl+C** stops the current work; changes already made are kept. What remains at the end is the project, the history of decisions and the commands by which the result can be checked.
