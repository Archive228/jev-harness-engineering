# JEVIS + Harness Engineering

[![Test harness](https://github.com/Archive228/jev-harness-engineering/actions/workflows/tests.yml/badge.svg)](https://github.com/Archive228/jev-harness-engineering/actions/workflows/tests.yml)

The full article and the lab where you can see the whole path: Choice, Score and Noul → a check of the requirements → diagnostic selection → a code repair → acceptance again.

**Start with the [ten-minute route](./START-HERE.md).** You end up with a repaired copy of a small application, a requirements report and a log of decisions. The first run works without keys, and the same tools can then be connected to the real Jev and Codex.

## What is already verified

- **83 automatic tests pass locally.** [Full output](./verification/terminal/unit-tests-83.txt).
- **Two live Jev sets:** 18 requests and 28 correct decisions in each. The article's first request was run separately with the Russian wording. These are small sets we assembled ourselves, not an assessment of reliability on arbitrary data.
- **Jev plus Codex together:** two defects repaired, and the third run stopped because of confidence 0.52 against a threshold of 0.60. After a copy of that state was explicitly switched to all diagnostics, Codex repaired the third defect too. The original stop is saved.
- **Nine offline scenarios:** six completions and three expected stops; no false `complete`.

The details and the limits of each experiment: [VALIDATION.md](./VALIDATION.md). Screenshots, terminal logs and links to the original JSON: [evidence gallery](./verification/evidence-gallery.en.html) ([in Russian](./verification/evidence-gallery.html)). The earlier experiment of 19 September, with `fixed` and without Jev, is saved separately: [three Codex runs](./verification/codex-worker-2026-09-19/evaluation.md).

## Reading and running

- The article, shortened edition: [English](./jev-engineering.en.v2.md) · [HTML](./jev-engineering.en.v2.html), [Russian](./jev-engineering.v2.md) · [HTML](./jev-engineering.v2.html).
- The full first edition: [English](./jev-engineering.en.jev-focus.md), [Russian](./jev-engineering.md) · [HTML](./jev-engineering.html).
- [The quick route for a reader](./START-HERE.md).
- [The lab and its commands](./jev-harness-lab/README.md).
- [Method for the live Jev evaluations](./jev-harness-lab/live-eval-method.md).
- [The diagrams in SVG/PNG](./assets/README.md).

You need Python 3.9+ and macOS/Linux. No external Python packages are needed. The repository is private for now: without GitHub access, unpack the article archive that came with the material and open the `jev-harness-lab` folder. If you do have access:

```bash
git clone https://github.com/Archive228/jev-harness-engineering.git
cd jev-harness-engineering/jev-harness-lab
```

From the `jev-harness-lab` folder:

```bash
python3 run.py loop --mode demo --case missing-evidence --out runs/my-first-loop
python3 -B -m unittest discover -s tests -v
```

Expect `complete`: five checks and one repair. In demo the real code and the real tests execute, while the judge's answers and the worker's change come from canned fixtures. To run it again, pick a new `--out`: existing results are not overwritten.

## Connecting the real Jev and Codex

Pass the TypeSafe key through the `TYPESAFE_API_KEY` environment variable. Authorise the Codex CLI and generate a config for your current local paths:

```bash
codex login status
python3 adapters/codex_cli.py --configure
python3 run.py inspect --mode live --case export-ticket
python3 live_eval.py --out runs/my-jev-primary
python3 live_eval.py --cases fixtures/live-eval-challenge-cases.json --out runs/my-jev-challenge
python3 worker_eval.py --selector jev --out runs/my-jev-codex
```

The first two evaluations make 18 TypeSafe requests each. `worker_eval.py --selector jev` runs three tasks against the real Jev and Codex and spends their limits; Codex is called only if the policy allowed a repair. The result may be a justified stop. [Adapter setup](./jev-harness-lab/codex-worker-setup.md).

To check Codex on its own, without Jev:

```bash
python3 worker_eval.py --selector fixed --out runs/my-codex-only
```

In this lab Noul only annotates the scope of a test. A failure of its API is stored in the report and does not overturn the deterministic acceptance. An error from the Choice router stops the loop. Tokens are counted from the counters that came back; `usage_complete` shows whether the data is complete. Zero known counters after an error do not mean the request was free.

## Building the HTML and checking CI

Editing the article needs Node >=20 and the npm lockfile:

```bash
npm ci --ignore-scripts
npm run build:article
```

The Python lab does not need Node. The workflow is set up for Python 3.9 / 3.12 / 3.13 / 3.14 and a separate check of the HTML build. For the result on a particular commit, see [GitHub Actions](https://github.com/Archive228/jev-harness-engineering/actions); the 83 local tests and an earlier green CI do not stand in for the status of the new configuration.

API keys and local configs with absolute paths are excluded from Git. After moving the directory, run `--configure` again.

## The interactive agent in the terminal

A finished chat with free-form input, real Codex actions and Jev decisions: [launch and first request](./terminal-agent/README.md). The command `terminal-agent/jev` opens an empty chat. Write a plain idea: «Хочу что-нибудь полезное про крипту, чтобы запустить прямо в терминале.» ("I want something useful about crypto, to run right in the terminal.") The agent helps you pin down the result, offers a plan with criteria to check against, and starts execution after the **"Start work"** button. You can correct the plan in your own words, and the exact task for the worker is visible in a separate tab. Questions and answers are saved between runs. That session was run in Russian, so its saved artefacts and the screenshots are in Russian; the English in brackets is a gloss, while the button names quoted here are the current interface strings.

**Enter** or the "Discuss" button sends the whole message; **Ctrl+J** adds a line. Shift+Enter works if the terminal supports it, and Ctrl+D remains an additional way to send. Pasting preserves every paragraph and sends nothing automatically. To execute an already exact task without any discussion, there are `--direct` and `/direct`.

In version 2: expandable tool cards, the Jev decisions panel on F6, session search, drafts, a file and diff viewer, Markdown export, the plan mode and the Jev assist/observe/off modes. `terminal-agent/jev --mission cryptolab` creates a separate teaching project for tracking crypto trades, with seven tests set in advance. [The chapter on the finished terminal agent](./terminal-agent/ARTICLE-TERMINAL-V2.md), [a review of the Pi/PiJev/OpenCode/Crush sources](./terminal-agent/research/upstream-audit.md), [the v2 checks](./terminal-agent/verification/v2/README.md).

The updated interface uses a pink accent, visible navigation buttons and a separate summary of the answer. After a successful completion "Activity" collapses; a click or Ctrl+O expands it. The "Files", "Copy" and "Export" buttons help you take the result away, and "Stop" is available while work is running. [The check of the updated interface](./terminal-agent/verification/ui-pink/README.md) is kept separate from the historical live v2 run.

The new path **idea → questions → plan → execution** was verified by building a terminal crypto calculator live. [The log, the code, the tests and the screenshots](./terminal-agent/verification/guided/README.md). The product uses adaptations of the open sources of OpenCode, Hermes and Codex; [the exact files, the licences and the limits of what was carried over](./terminal-agent/research/ATTRIBUTION.md) are kept in the repository.
