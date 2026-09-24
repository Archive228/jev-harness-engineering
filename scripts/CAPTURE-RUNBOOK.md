# Capturing the terminal screenshots

For the Claude session running on the Mac mini. Everything here produces real
screenshots: a real terminal window, running the real agent, captured with the
system screenshot tool. Nothing is rendered or mocked.

## Before you start

```bash
cd <repo>/article/terminal-agent && ./setup.sh
```

`setup.sh` creates `.venv` and installs the pinned dependencies. The capture
script refuses to run without it.

Check that the agent is fully English before capturing. A single Russian label in
a frame means the shot has to be retaken:

```bash
cd <repo>/article/terminal-agent && python3 -c "
import re, pathlib
bad = [str(p) for p in pathlib.Path('jev_agent').rglob('*')
       if p.is_file() and p.suffix in ('.py', '.md')
       and re.search(r'[Ѐ-ӿ]', p.read_text(encoding='utf-8', errors='ignore'))]
print('files with Russian:', bad or 'none')"
```

## The capture script

`scripts/capture-terminal.sh` drives one Terminal window.

```bash
./scripts/capture-terminal.sh open          # opens the window, starts the agent
./scripts/capture-terminal.sh send "text"   # types text and presses Return
./scripts/capture-terminal.sh enter         # presses Return on its own
./scripts/capture-terminal.sh shot NAME     # saves assets/screenshots/terminal/NAME.png
./scripts/capture-terminal.sh close         # closes the window
```

Three things it handles that a naive `screencapture` does not.

**Occlusion.** `screencapture -R` photographs a screen rectangle, so any window
that drifts on top lands in the frame instead. The script confirms our window is
the front window of the front application immediately before and immediately
after each shot, and throws the frame away otherwise. If it cannot get a clean
frame in six tries it fails rather than saving the wrong picture.

**Translucency.** Terminal's default profile lets the desktop show through, which
turns a screenshot of a terminal into a screenshot of your wallpaper. The script
switches the tab to an opaque profile. The default is `Novel`, whose cream
background matches the article's palette. Override with `JEVIS_PROFILE`, but check
first that the profile you pick has no alpha:

```bash
python3 -c "
import plistlib, subprocess, re
d = plistlib.loads(subprocess.run(['defaults','export','com.apple.Terminal','-'],capture_output=True).stdout)
for name, prof in sorted(d.get('Window Settings', {}).items()):
    bg = prof.get('BackgroundColor')
    m = re.search(r'([\d.]+ [\d.]+ [\d.]+(?: [\d.]+)?)', bg.decode('latin-1','ignore')) if isinstance(bg, bytes) else None
    comps = m.group(1).split() if m else []
    print(f'{name:18} {\"opaque\" if len(comps) == 3 else (\"alpha \" + comps[3] if len(comps) > 3 else \"unknown\")}')"
```

Four components means the last one is opacity, and anything below 1 will show the
desktop. Three components means opaque.

**The Dock.** The window is sized in character cells and then loses rows until it
clears the Dock, so the Dock cannot appear along the bottom edge. Geometry is
`JEVIS_COLS` (110) by `JEVIS_ROWS` (34) at position `JEVIS_X`, `JEVIS_Y`.

## What to capture

One file per state, in this order. Take each shot only after the screen has
settled: the agent redraws, and a frame caught mid-redraw looks broken.

| File | State |
|---|---|
| `01-start` | the opening screen, project header and status line |
| `02-intake` | the clarifying questions after a request is typed |
| `03-plan` | the proposed plan waiting for approval |
| `04-run` | work in progress, steps and tool output |
| `05-evidence` | the requirement report, with a check that failed |
| `06-stop` | a stop with its reason, and how to carry on |
| `07-status` | `/status`, showing project, session and worker |

Use `--demo`, so no keys are needed and no model is called. The mission
`--mission loglab` makes a fresh copy of the teaching project each time, so runs
are repeatable and nothing outside it is touched.

```bash
./scripts/capture-terminal.sh open
sleep 4
./scripts/capture-terminal.sh shot 01-start
```

Then drive the agent with `send` and `shot` between steps.

## After capturing

Record what you did, the way the other screenshots in this repo are recorded:
add the files to `assets/screenshots/manifest.json` with their SHA-256 and byte
size, note the machine and the capture method, and do not edit the image bytes.

Check every frame before it ships:

- no window other than the terminal anywhere in it
- no Dock, no menu bar, no desktop showing through
- no Russian text
- no absolute path that exposes anything beyond the project folder
- the text is legible at the width the article displays it
