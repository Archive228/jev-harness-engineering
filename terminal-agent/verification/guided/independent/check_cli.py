#!/usr/bin/env python3
"""Independent black-box checks for the calculator produced by the live demo.

No calculator functions are imported. Expected values below are written from
the accepted brief, and explicitly chosen additional examples. This is an
after-run audit, not an acceptance contract registered with the agent.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


LABELS = (
    "Затраты на покупку с комиссией",
    "Поступления после продажи и комиссии",
    "Общая комиссия",
    "Чистая прибыль / убыток",
    "Доходность относительно затрат",
)
BASE = ["100", "2", "120", "0", "0"]
BASE_EXPECTED = ["200,00", "240,00", "0,00", "40,00", "20,00%"]


def sha_files(workspace):
    return {
        path.relative_to(workspace).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(workspace.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    transcripts = output / "cases"
    transcripts.mkdir(exist_ok=True)
    before = sha_files(workspace)
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    results = []

    def run_case(name, inputs, expected=None, errors=0, exit_code=0):
        stdin = "\n".join(inputs) + ("\n" if inputs else "")
        start = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "crypto_profit.py"], cwd=workspace, input=stdin,
            text=True, capture_output=True, env=environment, timeout=5,
        )
        failures = []
        if completed.returncode != exit_code:
            failures.append("exit code %s != %s" % (completed.returncode, exit_code))
        if completed.stderr:
            failures.append("unexpected stderr")
        actual_errors = completed.stdout.count("Ошибка:")
        if actual_errors != errors:
            failures.append("error count %s != %s" % (actual_errors, errors))
        if expected is not None:
            for label, value in zip(LABELS, expected):
                if "%s: %s\n" % (label, value) not in completed.stdout:
                    failures.append("missing exact output: %s: %s" % (label, value))
        if exit_code == 1:
            if "Расчёт отменён: ввод прерван." not in completed.stdout:
                failures.append("missing cancellation explanation")
            if "Результат (" in completed.stdout:
                failures.append("calculation must not complete with missing input")
        record = {
            "name": name, "passed": not failures, "input_lines": inputs,
            "expected_values": expected, "expected_errors": errors,
            "expected_exit_code": exit_code, "actual_exit_code": completed.returncode,
            "failures": failures, "duration_ms": round((time.monotonic() - start) * 1000, 2),
        }
        results.append(record)
        transcript = [
            "CASE: " + name,
            "COMMAND: python3 crypto_profit.py",
            "STDIN (JSON lines, empty strings mean Enter): " + json.dumps(inputs, ensure_ascii=False),
            "EXPECTED VALUES: " + json.dumps(expected, ensure_ascii=False),
            "EXPECTED ERROR COUNT: " + str(errors),
            "EXIT CODE: " + str(completed.returncode),
            "STATUS: " + ("PASS" if not failures else "FAIL"),
            "STDOUT:", completed.stdout, "STDERR:", completed.stderr,
        ]
        (transcripts / (name + ".txt")).write_text("\n".join(transcript), encoding="utf-8")

    # Plan acceptance examples: constants are not calculated by production code.
    run_case("profit_without_fees", BASE, BASE_EXPECTED)
    run_case("profit_default_blank_fees", ["100", "2", "120", "", ""], BASE_EXPECTED)
    run_case("profit_one_percent_each", ["100", "2", "120", "1", "1"],
             ["202,00", "237,60", "4,40", "35,60", "17,62%"])
    run_case("loss", ["100", "2", "80", "0", "0"],
             ["200,00", "160,00", "0,00", "-40,00", "-20,00%"])
    run_case("break_even", ["100", "2", "100", "0", "0"],
             ["200,00", "200,00", "0,00", "0,00", "0,00%"])
    run_case("zero_sale_price", ["100", "2", "0", "0", "0"],
             ["200,00", "0,00", "0,00", "-200,00", "-100,00%"])
    # Additional independent arithmetic: 80 * 0.5 = 40; buy fee 0.8,
    # gross sale 50; sale fee 0.5; profit 8.7; 8.7 / 40.8 * 100 = 21.3235...
    run_case("comma_fractions_distinct_fees", ["80,0", "0,5", "100,0", "2,0", "1,0"],
             ["40,80", "49,50", "1,30", "8,70", "21,32%"])
    run_case("fee_below_upper_bound", ["100", "1", "100", "0", "99,99"],
             ["100,00", "0,01", "99,99", "-99,99", "-99,99%"])

    invalid_by_field = [
        ("buy_price", ["abc", "", "0", "-1", "NaN", "Inf", "-Infinity"]),
        ("quantity", ["abc", "", "0", "-1", "NaN", "Inf", "-Infinity"]),
        ("sell_price", ["abc", "", "-1", "NaN", "Inf", "-Infinity"]),
        ("buy_fee", ["abc", "-1", "100", "101", "NaN", "Inf", "-Infinity"]),
        ("sell_fee", ["abc", "-1", "100", "101", "NaN", "Inf", "-Infinity"]),
    ]
    for field_index, (field_name, invalid_values) in enumerate(invalid_by_field):
        for invalid in invalid_values:
            values = BASE.copy()
            values.insert(field_index, invalid)
            slug = invalid.replace("-", "minus_") or "empty"
            run_case("retry_%s_%s" % (field_name, slug), values, BASE_EXPECTED, errors=1)
    for accepted_fields in range(5):
        run_case("eof_after_%d_fields" % accepted_fields, BASE[:accepted_fields], exit_code=1)

    generated = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-v"], cwd=workspace,
        text=True, capture_output=True, env=environment, timeout=30,
    )
    generated_output = generated.stdout + generated.stderr
    (output / "generated-tests.txt").write_text(generated_output, encoding="utf-8")
    match = re.search(r"Ran (\d+) tests?", generated_output)
    after = sha_files(workspace)
    summary = {
        "description": "Independent after-run black-box CLI verification; no production functions imported",
        "python_version": sys.version.split()[0],
        "independent_cases": len(results),
        "independent_passed": sum(item["passed"] for item in results),
        "independent_failed": sum(not item["passed"] for item in results),
        "generated_suite": {
            "command": "python3 -m unittest discover -v",
            "exit_code": generated.returncode,
            "test_count": int(match.group(1)) if match else None,
            "passed": generated.returncode == 0,
        },
        "workspace_unchanged": before == after,
        "workspace_sha256": after,
        "cases": results,
    }
    (output / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = [
        "Independent CLI cases: %d/%d PASS" % (summary["independent_passed"], len(results)),
        "Generated test suite (reported separately): %s tests, exit %s" % (summary["generated_suite"]["test_count"], generated.returncode),
        "Workspace source files unchanged: %s" % summary["workspace_unchanged"],
        "Python: " + summary["python_version"], "",
    ]
    report.extend(("PASS " if item["passed"] else "FAIL ") + item["name"] for item in results)
    (output / "results.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report[:4]))
    return int(summary["independent_failed"] > 0 or generated.returncode != 0 or before != after)


if __name__ == "__main__":
    raise SystemExit(main())
