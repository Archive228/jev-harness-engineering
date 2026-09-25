# -*- coding: utf-8 -*-
"""Draw a diagram as terminal output: a character grid, box-drawing and colour.

The article's pictures sit next to screenshots of the agent, so they should look
like the thing they explain rather than like a drawing tool. Everything here is
text on a fixed grid in the interface's own palette, read out of jev_agent/tui.py.

Alignment is the whole problem with monospace in SVG: the advance width depends on
which font the reader actually has. Every run is therefore emitted with an explicit
textLength of exactly len(text) x CELL, so a column lands in the same place whether
the page renders in Menlo, Consolas or a fallback.
"""
from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent

MONO = "Menlo, 'SF Mono', Consolas, 'DejaVu Sans Mono', monospace"
SIZE = 20
CELL = 12.0          # advance per character
LINE = 27.0          # baseline to baseline
PAD_X, PAD_TOP = 26, 30

C = {
    "bg": "#18151d",
    "panel": "#221c29",
    "ink": "#eee8f1",
    "muted": "#aaa0b2",
    "dim": "#7d7188",
    "accent": "#f2a0cc",
    "accent2": "#c98fd8",
    "line": "#5d4a68",
    "ok": "#9fd6a8",
    "fail": "#ee9b9b",
    "warn": "#e8c98a",
}

# box drawing
TL, TR, BL, BR, H, V = "╭", "╮", "╰", "╯", "─", "│"


class Term:
    def __init__(self, cols, rows, title, desc, chrome=True):
        self.cols, self.rows, self.chrome = cols, rows, chrome
        self.top = PAD_TOP + (44 if chrome else 0)
        w = round(PAD_X * 2 + cols * CELL)
        h = round(self.top + rows * LINE + PAD_TOP)
        self.w, self.h = w, h
        self.s = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(title)}</title>',
            f'<desc id="desc">{escape(desc)}</desc>',
            f'<rect x="0" y="0" width="{w}" height="{h}" rx="14" fill="{C["bg"]}"/>',
        ]
        if chrome:
            self.s.append(f'<rect x="0" y="0" width="{w}" height="44" rx="14" fill="{C["panel"]}"/>')
            self.s.append(f'<rect x="0" y="30" width="{w}" height="14" fill="{C["panel"]}"/>')
            for i, col in enumerate(("#ee9b9b", "#e8c98a", "#9fd6a8")):
                self.s.append(f'<circle cx="{24 + i * 22}" cy="22" r="6.5" fill="{col}"/>')
            self.raw_text(w / 2, 28, title, size=15, fill=C["muted"], anchor="middle")

    # ── primitives ────────────────────────────────────────────────────────────
    def raw_text(self, x, y, text, size=SIZE, fill=None, weight=400, anchor="start"):
        self.s.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{MONO}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill or C["ink"]}" text-anchor="{anchor}" '
            f'xml:space="preserve">{escape(text)}</text>')

    def put(self, row, col, text, fill=None, weight=400):
        """Place text at a grid cell, pinned to exactly len(text) columns."""
        if not text:
            return
        x = PAD_X + col * CELL
        y = self.top + row * LINE + SIZE * 0.78
        self.s.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{MONO}" font-size="{SIZE}" '
            f'font-weight="{weight}" fill="{fill or C["ink"]}" xml:space="preserve" '
            f'textLength="{len(text) * CELL:.1f}" lengthAdjust="spacing">{escape(text)}</text>')

    def runs(self, row, col, parts):
        """parts: [(text, fill), ...] laid out left to right on one line."""
        for text, fill in parts:
            self.put(row, col, text, fill=fill)
            col += len(text)
        return col

    # ── composites ────────────────────────────────────────────────────────────
    def panel(self, row, col, width, height, title=None, title_fill=None):
        """A rounded box. width and height are in cells, borders included."""
        inner = width - 2
        if title:
            label = f" {title} "
            left = 1
            bar = H * left + label + H * (inner - left - len(label))
            self.put(row, col, TL, fill=C["line"])
            self.put(row, col + 1, H * left, fill=C["line"])
            self.put(row, col + 1 + left, label, fill=title_fill or C["accent"], weight=700)
            self.put(row, col + 1 + left + len(label), H * (inner - left - len(label)), fill=C["line"])
            self.put(row, col + width - 1, TR, fill=C["line"])
        else:
            self.put(row, col, TL + H * inner + TR, fill=C["line"])
        for r in range(row + 1, row + height - 1):
            self.put(r, col, V, fill=C["line"])
            self.put(r, col + width - 1, V, fill=C["line"])
        self.put(row + height - 1, col, BL + H * inner + BR, fill=C["line"])

    def rule(self, row, col, width, title=None, fill=None):
        """A fastfetch-style divider with a centred caption."""
        if not title:
            self.put(row, col, H * width, fill=fill or C["line"])
            return
        label = f" {title} "
        left = (width - len(label)) // 2
        self.put(row, col, H * left, fill=fill or C["line"])
        self.put(row, col + left, label, fill=C["accent"], weight=700)
        self.put(row, col + left + len(label), H * (width - left - len(label)), fill=fill or C["line"])

    def row(self, r, col, label, value, label_w=16, tick="├─ ", label_fill=None, value_fill=None):
        c = self.runs(r, col, [(tick, C["line"]),
                               (label.ljust(label_w), label_fill or C["accent"])])
        self.put(r, c, value, fill=value_fill)

    def bar(self, r, col, width, frac, fill=None):
        full = max(0, min(width, round(frac * width)))
        self.runs(r, col, [("[", C["line"]),
                           ("█" * full, fill or C["accent"]),
                           ("░" * (width - full), C["line"]),
                           ("]", C["line"])])

    def arrow_right(self, r, col, length=3):
        self.put(r, col, H * (length - 1) + "▶", fill=C["accent"])

    def arrow_down(self, r, col):
        self.put(r, col, "▼", fill=C["accent"])

    def dots(self, r, col, n=8):
        palette = [C["fail"], C["warn"], C["ok"], "#8fd8d0", C["accent2"], C["accent"],
                   "#b9a0e8", C["muted"]]
        for i in range(n):
            self.put(r, col + i * 2, "●", fill=palette[i % len(palette)])

    def save(self, name):
        self.s.append("</svg>")
        xml = "\n".join(self.s)
        ET.fromstring(xml)
        (ROOT / name).write_text(xml, encoding="utf-8")
        return name
