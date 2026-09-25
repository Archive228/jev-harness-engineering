# Terminal agent checks · 20 September 2026

The historical protocol of the first version. The current build of the interface and the engine was checked separately: [v2 · 21 September](./v2/README.md).

**53 tests: PASS** on Python 3.9.6.

`unit-tests.txt` holds the full output of the engine, subprocess, mission and terminal interface checks. The UI tests paste multi-line text whole, check Enter as a line break, sending with Ctrl+D and with the button, F4 for the large editor, carry on a conversation, open the menu, save an SVG, resize the terminal and stop an active task. Stand-in model answers are used only in the automated tests.

## A real free-form request

`live-build.jsonl` is a new request into an **empty** workspace: build an incident analyser, the data, two kinds of report and tests. Jev picked `implement`. Codex produced a multi-file result, ran its own 28 tests and the CLI, then found a further Unicode defect. The initial limit of 300 seconds stopped the process before the final answer. This is saved as `error`, not as a success.

`live-build-resume.jsonl` is the real continuation of the same session. Codex added a regression test, first got a real FAIL on the corrupted Unicode, fixed the handling and reached **29 PASS**. The harness then reran the discovered unittest set independently of what the worker said: 29 PASS, and the snapshot before and after the check was the same. Jev review returned its judgement on the actual results. The outcome is `ready`: the result was prepared, and a free-form task has no separate oracle set in advance.

The continuation took 72.68 seconds, with 2 Jev calls and 1 Codex call. The original generation and the stop are not hidden. The current version allows 480 seconds per worker attempt and 900 per turn: the raised limit is a setting of the program, not a promise to finish any request within that time.

The full portable copy is [live-build-session](./live-build-session/). Inside it, `workspace/` holds the real tool the agent created, and `turn-002/attempt-01-checks.json` is the harness rerun of the checks. Confirmed: the commands ran and the listed tests passed. Exhaustive correctness of an arbitrary analyser is not claimed.

## A live conversation and a follow-up

`live-chat-smoke.jsonl` and `live-followup.jsonl` hold two real conversational turns. Under the first version of the instructions the worker inaccurately called Jev a wrapper. The worker's context was made more precise: Jev is a TypeSafe model, Codex is the generative worker, Python is the harness. In the next turn of the saved session the worker explained the difference correctly. The raw first answer is left in the log.

## Screens

`screenshots/terminal-empty.svg` and `terminal-empty-color.svg` were saved with **Ctrl+S from a TUI actually running in a PTY**. The first run inherited `NO_COLOR=1` from the automation environment; the second used an ordinary truecolor terminal. `terminal-live-work.svg` is a static snapshot of viewing the actual accumulated events through the same interface, and it is explicitly marked «ЗАПИСЬ», the replay marker; in the English build of `jev_agent/tui.py` this state is labelled `Replay`. The session was driven in Russian, so the screenshots here mix Russian panel labels with English phase and status names: the masthead reads `JEV + HARNESS`, and the graph rows read `REQUEST`, `JEV ROUTE`, `POLICY`, `CODEX`. The labels quoted from them and the answer texts in the saved session logs are in Russian; the test output in `unit-tests.txt` is in English. No actions and no answers were invented for the picture. `terminal-result.svg` is a Ctrl+S from the TUI after a finished real session was opened with `--resume`: the saved result and the line ready for the next message are visible. The PNGs with the `browser` suffix are browser renderings of the saved SVG.

## Reproducibility

Keys and local sessions are not part of Git. In the distributed JSON and logs the author's path is replaced with `<checkout>`. The program files and the values of the real answers are kept. `dependency-install.json` records the dependencies verified against the SHA-256 of the official PyPI; the test client uses `jev-1.13.0`, and the Codex CLI uses the currently configured model with no override.

## Multi-line paste

`terminal-multiline.svg` was saved with Ctrl+S from a real TUI in a PTY after a bracketed paste of the crypto prompt and F4. All 27 lines (1111 characters) are visible, along with the «ЖДУ ЗАДАЧУ» state ("WAITING FOR A TASK") and the «Отправить · Ctrl+D» button ("Send · Ctrl+D"). The paste itself called no model. The full text is sent in one turn only after an explicit send; this is checked through the standard Paste event, the keyboard and the button in the UI tests.

The full run also revealed a race in resending SIGKILL after the process group had already finished in the macOS sandbox. Termination was made idempotent: a signal that succeeded is not sent again, and a denial of the first signal is not hidden. Both scenarios are covered by separate regression tests.
