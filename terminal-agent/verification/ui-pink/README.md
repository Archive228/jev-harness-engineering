# Checks of the updated terminal interface

21 September 2026. A pink theme, explicit navigation, multi-line input, collapsible actions and a separate final answer.

## Automated checks

`python -B -m unittest discover -s tests -v`: **129 tests, OK**, Python 3.9.6. Full output: [unit-tests.txt](./unit-tests.txt); the command, the duration and the exit code: [unit-tests.json](./unit-tests.json).

The scenarios check sending the whole message with Enter, pasting without an automatic send, line breaks, keeping the draft when work is stopped, a new chat, the search over sessions and files, copying the full answer, export, a long history and the placement of the buttons in an 80×24 terminal. Separate regression tests reproduce the scroll conflict on restore and the autosave race when sessions are switched. The tests call no models.

## The real terminal

The application was run in a 126×48 PTY with `TERM=xterm-256color` and `COLORTERM=truecolor`. This is the application's current interface. For the result and Jev screens, a copy of [the real v2 crypto run](../v2/README.md) was opened. No new model calls were made during this check, and the saved results are not presented as a new run.

- [The final answer and the result buttons](../screenshots/terminal-pink-result-browser.png) · [the source SVG](../screenshots/terminal-pink-result.svg).
- [Activity expanded](../screenshots/terminal-pink-activity-browser.png) · [SVG](../screenshots/terminal-pink-activity.svg). The interface in this run was in Russian, so Activity appears on the screen as «Ход работы».
- [The graph and the Jev answers](../screenshots/terminal-pink-jev-browser.png) · [SVG](../screenshots/terminal-pink-jev.svg).
- [The editor with a large message](../screenshots/terminal-pink-input-browser.png) · [SVG](../screenshots/terminal-pink-input.svg).

Actions in the terminal: restoring the history, Ctrl+O, F6, Escape, Ctrl+N, pasting 13 lines / 517 characters, F4, Ctrl+S, exit. The request stayed in the editor, and the new session received no execution event at all. [The request itself](./input-draft.txt) and [the terminal recording with the ANSI sequences](./terminal-session.ansi) are saved.

The SVGs come from the standard Ctrl+S in the running application. The PNGs are browser captures of those SVGs, with no redrawing of the content. [capture.json](./capture.json) holds the SHA-256 hashes, the terminal size and the check that the source events are unchanged.

## What was adapted from other agents

From Pi: the compact action cards and expanding the details with Ctrl+O. From OpenCode: sending with Enter and a new line with Ctrl+J, and the search over commands and sessions. No complete external shell was carried over: this is our own Textual interface, wired to the events of our Python harness. The sources, the pinned versions and the limits of what was borrowed are described in [the study of the repositories](../../research/upstream-audit.md).
