#!/usr/bin/env python3
"""Convert incident JSONL to a machine report and a human report."""
import argparse
import json
from pathlib import Path

from loglab_core.pipeline import analyze
from loglab_core.render import markdown_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_output")
    parser.add_argument("--markdown", type=Path, required=True, dest="markdown_output")
    args = parser.parse_args()
    report = analyze(args.input.read_text(encoding="utf-8"))
    for target in (args.json_output, args.markdown_output):
        target.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown_report(report), encoding="utf-8")
    print("Analyzed %d events; JSON and Markdown reports saved." % report["total_events"])


if __name__ == "__main__":
    main()
