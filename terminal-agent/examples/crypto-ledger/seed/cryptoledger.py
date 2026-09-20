"""Offline CSV ledger; all sample data is synthetic."""
import argparse
import csv
import json
from pathlib import Path

from ledger import analyze


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", required=True, type=Path)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8", newline="") as source:
        report = analyze(csv.DictReader(source))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saved " + str(args.json))


if __name__ == "__main__":
    main()
