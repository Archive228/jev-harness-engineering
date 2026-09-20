"""Offline CSV ledger; all sample data is synthetic."""
import argparse
import csv
import json
import sys
from pathlib import Path

from ledger import CSV_FIELDS, analyze


def _rows(reader):
    """Keep recoverable CSV parser failures in the rejected-row count."""
    while True:
        try:
            row = next(reader)
        except StopIteration:
            return
        except csv.Error as error:
            yield csv.Error(f"физическая строка {reader.reader.line_num}: {error}")
        else:
            yield row


def main():
    parser = argparse.ArgumentParser(description="Учёт количества и денежных потоков в USDT по CSV.")
    parser.add_argument("input", type=Path, help="CSV с синтетическими сделками")
    parser.add_argument("--json", required=True, type=Path, help="путь для JSON-отчёта")
    args = parser.parse_args()
    if args.input.resolve() == args.json.resolve():
        parser.error("входной CSV и выходной JSON должны быть разными файлами")
    try:
        with args.input.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            if reader.fieldnames is not None and (
                len(reader.fieldnames) != len(CSV_FIELDS) or set(reader.fieldnames) != set(CSV_FIELDS)
            ):
                raise ValueError("заголовок CSV должен содержать поля: " + ",".join(CSV_FIELDS))
            report = analyze(_rows(reader))
    except (OSError, UnicodeError, csv.Error, ValueError) as error:
        parser.exit(2, f"Ошибка чтения {args.input}: {error}\n")
    try:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8")
    except OSError as error:
        parser.exit(2, f"Ошибка записи {args.json}: {error}\n")
    for warning in report["warnings"]:
        print(f"Предупреждение: {warning}", file=sys.stderr)
    print(f"Сохранён {args.json}: accepted_rows={report['accepted_rows']}, "
          f"duplicate_rows={report['duplicate_rows']}, rejected_rows={report['rejected_rows']}")


if __name__ == "__main__":
    main()
