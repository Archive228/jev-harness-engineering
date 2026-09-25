# Article illustrations

Every diagram is editable SVG. PNGs of the same size are prepared for platforms that do not accept SVG. The vector originals depend on no external fonts or resources. Main font: the system sans-serif. Every diagram has accessible `title` and `desc`.

- `01-jev-interface.svg` · 1480 × 760. The API contract: state and questions → Jev → typed answers → an action taken by ordinary code. The internal architecture of the model is not depicted.
- `02-three-primitives.svg` · 1480 × 1080. One example of state and three independent questions. The criteria set and the shapes of the answer are shown; no probabilities, real or invented, are given. The values 0/1/2 stand for the levels of the chosen scale, and 0/0.5/1 for the meaning of the Noul range.
- `03-three-builds.svg` · 1480 × 1160. Noul helps relate evidence to a requirement, Choice picks an extra diagnostic; the programmatic policy runs the mandatory checks, sets the limits and closes the loop.
- `04-run-trace.svg` · 1480 × 1290. An explicitly labelled offline scenario: R2 → C2 FAIL → a prepared D2 choice → a repair → a fresh snapshot → C1/C2 PASS → COMPLETE. The diagram is not the output of a live Jev API.

SVG generation: `python3 build_diagrams.py` (Python standard library only). The PNGs were exported with Sharp. All four images were inspected visually after export: no clipping and no overlapping text were found.

## English versions

Diagrams `01`–`07` exist in two languages. The Russian labels are drawn by `build_diagrams.py` (01–04) and `build_diagrams_jev.py` (05–07); the `-en` variants are drawn by `build_diagrams_en_base.py` (01–04) and `build_diagrams_jev_en.py` (05–07). Geometry and palette are shared, and the English labels were kept shorter so that nothing runs outside its block. Checked in a browser: no `<text>` element extends past its container.

```bash
python3 build_diagrams_en_base.py   # 01-04 -en
python3 build_diagrams_jev_en.py    # 05-07 -en
```

## English variants

The English article's diagrams are not drawings. Each one is terminal output: a character grid in
the interface's own palette, read out of `jev_agent/tui.py`, so a diagram and the screenshot below
it read as the same object.

```bash
python3 build_diagrams_term.py     # 01-09, the English set
```

`termcanvas.py` holds the grid. Alignment is the one hard part of monospace in SVG, because the
advance width depends on which font the reader actually has: every run is emitted with an explicit
`textLength` of exactly `len(text) x CELL`, so a column lands in the same place in Menlo, in
Consolas or in a fallback.

Palette, taken from the interface and not invented here:

```text
background  #18151d     panel   #221c29     text    #eee8f1
muted       #aaa0b2     accent  #f2a0cc     pass    #9fd6a8
border      #5d4a68     dim     #7d7188     fail    #ee9b9b
```

Two of the nine are new: `08-agent-map-en.svg` maps the screen region by region, and
`09-stop-anatomy-en.svg` shows the four inputs of one stopped turn and the policy that is the only
thing allowed to end it.

The Russian article keeps the earlier light drawings, built by `build_diagrams.py` and
`build_diagrams_jev.py`.
