# Experiment screenshots

Captured on 20 September 2026 in a browser from the local [results gallery](../../verification/evidence-gallery.html). The gallery reads the saved JSON and command output. Its source is [build-evidence.py](../../scripts/build-evidence.py). These are screenshots of a browser view of our own records, not of the TypeSafe interface and not of the native Terminal.

Four captures are embedded in the article:

- `01-live-primitives.png`: the real Russian request, three Jev answers and usage.
- `02-live-evaluations.png`: two separate labelled matrices of 28 decisions each.
- `03-live-loop-and-recovery.png`: the original two completions and one stop, then the separate recovery.
- `04-tests-and-terminal.png`: the actual result of 83 tests and a fragment of the saved stdout/stderr.

`mobile-gallery-check.png` and `mobile-loop-check.png` were saved while checking the responsive layout. Viewport sizes, SHA-256 and the sizes of the original files are in [manifest.json](./manifest.json). The screenshot bytes were not edited. The diagrams of how Jev and the harness are built sit one level up as editable SVG and PNG.

Full text logs are in [verification/terminal](../../verification/terminal/), and the requests and responses are in [verification/jev-live-2026-09-20](../../verification/jev-live-2026-09-20/). A screenshot helps you read a result. The corresponding JSON or log remains the source of the numbers.

English captures of the same gallery sit next to them with the `.en.png` suffix. Their description is in [README.en.md](./README.en.md).
