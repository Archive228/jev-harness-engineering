# Experiment screenshots (English)

Captured on 24 September 2026 from the local [English evidence gallery](../../verification/evidence-gallery.en.html). The gallery reads the same saved JSON and command output as the Russian one; its builder is [build-evidence-en.py](../../scripts/build-evidence-en.py), which is generated from [build-evidence.py](../../scripts/build-evidence.py) by [make-evidence-en.py](../../scripts/make-evidence-en.py). Only the chrome differs between the two galleries, so their numbers cannot drift apart.

These are screenshots of a browser view of our own records, not of the TypeSafe interface and not of a native terminal.

Four captures are embedded in the English article:

- `01-live-primitives.en.png`: the real request, three Jev answers and usage.
- `02-live-evaluations.en.png`: two separate labelled matrices of 28 decisions each.
- `03-live-loop-and-recovery.en.png`: the original two completions and one stop, then the separate recovery.
- `04-tests-and-terminal.en.png`: the actual result of 83 tests and a fragment of the saved stdout/stderr.

Two strings inside the images stay in Russian on purpose. The ticket text and the Score legend are what was actually sent to the API in the first call, and replacing them would misreport the experiment. The gallery labels that block accordingly, and the article explains why the first call was written in Russian.

Viewport, SHA-256 and byte sizes are in [manifest.json](./manifest.json) under `images_en`. Captured with headless Google Chrome at 1100x750 and device scale 1. The screenshot bytes were not edited.

Full text logs are in [verification/terminal](../../verification/terminal/), and the requests and responses are in [verification/jev-live-2026-09-20](../../verification/jev-live-2026-09-20/). A screenshot helps you read a result. The JSON or the log behind it remains the source of the numbers.
