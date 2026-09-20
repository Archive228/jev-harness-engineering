import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from incident_analyzer import analyze, parse_timestamp, render_markdown


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "incident_analyzer.py"
SAMPLE = ROOT / "examples" / "related_failures.jsonl"


def event(event_id="e1", timestamp="2026-09-19T09:00:00Z", service="database", **fields):
    result = dict(event_id=event_id, timestamp=timestamp, service=service,
                  level="ERROR", reason="Connection pool exhausted")
    result.update(fields)
    return result


def encoded(*events):
    return io.BytesIO("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in events).encode("utf-8"))


def pair(**overrides):
    upstream = event("up", trace_id="t1")
    downstream = event("down", "2026-09-19T09:00:02Z", "api", reason="Database timeout",
                       trace_id="t1", upstream_service="database")
    downstream.update(overrides)
    return upstream, downstream


class TimestampTests(unittest.TestCase):
    def test_equal_instants_with_different_offsets(self):
        expected = parse_timestamp("2026-09-19T09:00:00Z")
        for value in ("2026-09-19T12:00:00+03:00", "2026-09-19T05:00:00-04:00",
                      "2026-09-19T14:30:00+05:30"):
            with self.subTest(value=value):
                self.assertEqual(parse_timestamp(value), expected)

    def test_utc_order_across_midnight_and_microseconds(self):
        report = analyze(encoded(
            event("later", "2026-09-18T23:30:00-04:00"),
            event("first", "2026-09-19T02:00:00.000001+03:00"),
            event("middle", "2026-09-18T23:00:00.000002Z"),
        ))
        self.assertEqual([e["event_id"] for e in report["facts"]["events"]], ["first", "middle", "later"])
        self.assertEqual(report["facts"]["groups"][0]["first_seen"], "2026-09-18T23:00:00.000001Z")
        self.assertEqual(report["facts"]["groups"][0]["last_seen"], "2026-09-19T03:30:00Z")

    def test_repeated_local_hour_has_distinct_instants(self):
        early = parse_timestamp("2026-11-01T01:30:00-04:00")
        late = parse_timestamp("2026-11-01T01:30:00-05:00")
        self.assertEqual((late - early).total_seconds(), 3600)

    def test_invalid_or_ambiguous_timestamp(self):
        values = [None, 123, "", "2026-09-19", "2026-09-19T09:00:00", "2026-02-30T09:00:00Z",
                  "2026-09-19T09:00:00+24:00", "2026-09-19T09:00:00+01:60",
                  "2026-09-19T09:00:00-00:00", "0001-01-01T00:00:00+01:00",
                  "9999-12-31T23:59:59-01:00", "2026-09-19T09:00:00.1234567Z"]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_timestamp(value)


class InputTests(unittest.TestCase):
    def test_identical_and_conflicting_duplicates_first_valid_wins(self):
        original = event(trace_id="t1")
        report = analyze(encoded(original, dict(original, timestamp="2026-09-19T12:00:00+03:00"),
                                 dict(original, reason="Different reason")))
        self.assertEqual(report["statistics"]["duplicate_events"], 2)
        self.assertEqual(report["statistics"]["conflicting_duplicates"], 1)
        self.assertEqual(report["statistics"]["analyzed_errors"], 1)
        self.assertEqual(report["facts"]["events"][0]["reason"], original["reason"])
        self.assertEqual(report["warnings"][0]["line"], 3)
        self.assertEqual(report["warnings"][0]["event_id"], "e1")

    def test_invalid_record_does_not_reserve_id(self):
        report = analyze(encoded(event(timestamp="broken"), event()))
        self.assertEqual(report["statistics"]["invalid_lines"], 1)
        self.assertEqual(report["statistics"]["unique_events"], 1)
        self.assertEqual(report["statistics"]["duplicate_events"], 0)

    def test_grouping_uses_service_and_normalized_reason(self):
        report = analyze(encoded(event("a"), event("b", reason=" CONNECTION   POOL\texhausted "),
                                 event("c", reason="DNS failed"), event("d", service="api")))
        groups = {(g["service"], g["reason"]): g for g in report["facts"]["groups"]}
        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[("database", "connection pool exhausted")]["count"], 2)
        self.assertEqual(groups[("database", "connection pool exhausted")]["event_ids"], ["a", "b"])

    def test_broken_json_schema_and_encoding_do_not_stop_reading(self):
        bad = [b'{broken}\n', b'[]\n', b'null\n', b'\xff\n', b'{"value":NaN}\n',
               b'{"x":1,"x":2}\n', b'{"value":Infinity}\n']
        for overrides in ({"event_id": 42}, {"service": " "}, {"level": "unknown"},
                          {"reason": None}, {"trace_id": None}, {"upstream_service": ""},
                          {"timestamp": "2026-09-19T09:00:00"}, {"reason": "\ud800"}):
            bad.append((json.dumps(event(**overrides)) + "\n").encode("ascii"))
        missing = event()
        del missing["level"]
        bad.append((json.dumps(missing) + "\n").encode("ascii"))
        report = analyze(io.BytesIO(b"".join(bad) + encoded(event()).getvalue()))
        self.assertEqual(report["statistics"]["invalid_lines"], len(bad))
        self.assertEqual(report["statistics"]["analyzed_errors"], 1)
        self.assertEqual([w["line"] for w in report["warnings"]], list(range(1, len(bad) + 1)))

    def test_bom_blank_lines_and_empty_input(self):
        report = analyze(io.BytesIO(b'\xef\xbb\xbf\n \t\n' + encoded(event()).getvalue()))
        self.assertEqual(report["statistics"]["blank_lines"], 2)
        self.assertEqual(report["statistics"]["invalid_lines"], 0)
        empty = analyze(io.BytesIO(b""))
        self.assertEqual(empty["facts"]["events"], [])
        self.assertEqual(empty["hypotheses"], [])
        self.assertIn("Ошибок нет.", render_markdown(empty))

    def test_only_error_levels_are_grouped(self):
        levels = ["error", "critical", "fatal", "info", "DEBUG", "WARNING", "WARN"]
        report = analyze(encoded(*(event(str(i), level=level) for i, level in enumerate(levels))))
        self.assertEqual(report["statistics"]["analyzed_errors"], 3)
        self.assertEqual(report["statistics"]["non_error_events_in_period"], 4)

    def test_period_is_inclusive_and_compares_utc(self):
        report = analyze(encoded(event("before", "2026-09-19T08:59:59Z"),
                                 event("start", "2026-09-19T12:00:00+03:00"),
                                 event("end", "2026-09-19T05:01:00-04:00"),
                                 event("after", "2026-09-19T09:01:01Z")),
                         since=parse_timestamp("2026-09-19T09:00:00Z"),
                         until=parse_timestamp("2026-09-19T12:01:00+03:00"))
        self.assertEqual([e["event_id"] for e in report["facts"]["events"]], ["start", "end"])
        self.assertEqual(report["statistics"]["events_outside_period"], 2)

    def test_deduplication_precedes_period_and_level_filters(self):
        report = analyze(encoded(event(timestamp="2026-09-19T08:00:00Z"), event(),
                                 event("info-first", level="INFO"), event("info-first")),
                         since=parse_timestamp("2026-09-19T09:00:00Z"))
        self.assertEqual(report["statistics"]["analyzed_errors"], 0)
        self.assertEqual(report["statistics"]["events_outside_period"], 1)
        self.assertEqual(report["statistics"]["non_error_events_in_period"], 1)
        self.assertEqual(report["statistics"]["conflicting_duplicates"], 2)

    def test_invalid_settings(self):
        for window in (-1, 86401, True, 0.5):
            with self.subTest(window=window), self.assertRaises(ValueError):
                analyze(io.BytesIO(), window_seconds=window)
        with self.assertRaises(ValueError):
            analyze(io.BytesIO(), since=parse_timestamp("2026-09-19T09:00:00Z").replace(tzinfo=None))
        with self.assertRaises(ValueError):
            analyze(io.BytesIO(), since=parse_timestamp("2026-09-20T09:00:00Z"),
                    until=parse_timestamp("2026-09-19T09:00:00Z"))


class CorrelationTests(unittest.TestCase):
    def test_pair_has_evidence_but_no_proven_cause(self):
        upstream, downstream = pair(timestamp="2026-09-19T05:00:02-04:00")
        report = analyze(encoded(downstream, upstream))
        hypothesis = report["hypotheses"][0]
        self.assertEqual(hypothesis["evidence_event_ids"], ["up", "down"])
        self.assertEqual(hypothesis["observed_links"][0]["delay_seconds"], 2)
        self.assertEqual(hypothesis["status"], "hypothesis")
        self.assertFalse(report["root_cause"]["established"])
        self.assertTrue(hypothesis["verification_steps"])

    def test_time_proximity_alone_does_not_link_errors(self):
        for changed in ({"trace_id": "other"}, {"upstream_service": "redis"},
                        {"timestamp": "2026-09-19T08:59:59Z"},
                        {"timestamp": "2026-09-19T09:02:00.000001Z"}, {"level": "INFO"}):
            with self.subTest(changed=changed):
                self.assertEqual(analyze(encoded(*pair(**changed)))["hypotheses"], [])
        for missing in ("trace_id", "upstream_service"):
            upstream, downstream = pair()
            del downstream[missing]
            self.assertEqual(analyze(encoded(upstream, downstream))["hypotheses"], [])

    def test_window_boundary_and_simultaneous_events(self):
        for timestamp, window, expected in [("2026-09-19T09:02:00Z", 120, 1),
                                            ("2026-09-19T09:02:00Z", 119, 0),
                                            ("2026-09-19T09:00:00Z", 0, 1),
                                            ("2026-09-19T09:00:00.000001Z", 0, 0)]:
            with self.subTest(timestamp=timestamp, window=window):
                report = analyze(encoded(*pair(timestamp=timestamp)), window_seconds=window)
                self.assertEqual(len(report["hypotheses"]), expected)
                self.assertFalse(report["root_cause"]["established"])

    def test_same_service_cannot_link_to_itself(self):
        self.assertEqual(analyze(encoded(*pair(service="database")))["hypotheses"], [])

    def test_earliest_supported_datetime_does_not_overflow(self):
        upstream, downstream = pair(timestamp="0001-01-01T00:00:01Z")
        upstream["timestamp"] = "0001-01-01T00:00:00Z"
        self.assertEqual(len(analyze(encoded(upstream, downstream))["hypotheses"]), 1)

    def test_all_same_timestamp_candidates_preserve_evidence(self):
        upstream, downstream = pair()
        report = analyze(encoded(upstream, dict(upstream, event_id="up-2"), downstream))
        self.assertEqual(len(report["hypotheses"]), 1)
        self.assertEqual(report["hypotheses"][0]["evidence_event_ids"], ["up", "up-2", "down"])
        self.assertEqual(len(report["hypotheses"][0]["observed_links"]), 2)

    def test_sample_related_failures_and_false_lead(self):
        with SAMPLE.open("rb") as handle:
            report = analyze(handle)
        self.assertEqual(report["statistics"], {
            "total_lines": 12, "blank_lines": 0, "invalid_lines": 2, "duplicate_events": 2,
            "conflicting_duplicates": 1, "unique_events": 8, "events_outside_period": 0,
            "non_error_events_in_period": 1, "analyzed_errors": 7,
        })
        self.assertEqual(len(report["facts"]["groups"]), 4)
        self.assertEqual(report["facts"]["unlinked_event_ids"], ["noise-001"])
        self.assertEqual([(h["upstream_service"], h["downstream_service"]) for h in report["hypotheses"]],
                         [("api", "web"), ("database", "api")])
        for hypothesis in report["hypotheses"]:
            self.assertEqual(len(hypothesis["observed_links"]), 2)
            self.assertEqual(len(hypothesis["evidence_event_ids"]), 4)
            self.assertNotIn("noise-001", hypothesis["evidence_event_ids"])
        markdown = render_markdown(report)
        self.assertIn("## Факты из журнала", markdown)
        self.assertIn("## Гипотезы о причине", markdown)
        self.assertIn("Первопричина не доказана", markdown)

    def test_output_is_deterministic_without_duplicates(self):
        upstream, downstream = pair()
        self.assertEqual(analyze(encoded(upstream, downstream)), analyze(encoded(downstream, upstream)))

    def test_markdown_escapes_untrusted_log_content(self):
        markdown = render_markdown(analyze(encoded(event(reason="<script>alert(1)</script>\n# title [click](url)"))))
        self.assertNotIn("<script>", markdown)
        self.assertNotIn("\n# title", markdown)
        self.assertNotIn("[click](url)", markdown)
        self.assertIn("&lt;script&gt;", markdown)


class CliTests(unittest.TestCase):
    def setUp(self):
        # Все временные файлы тестов остаются внутри выбранной рабочей папки.
        self.temporary = tempfile.TemporaryDirectory(prefix=".test-incidents-", dir=ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.workdir = Path(self.temporary.name)

    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=self.workdir,
                              input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              encoding="utf-8", timeout=15)

    def test_cli_writes_both_reports_and_emits_warnings(self):
        result = self.run_cli(SAMPLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count("Предупреждение:"), 3)
        self.assertIn("строка 10", result.stderr)
        self.assertIn("строка 11", result.stderr)
        self.assertIn("строка 12", result.stderr)
        report = json.loads((self.workdir / "reports/incidents.json").read_text(encoding="utf-8"))
        markdown = (self.workdir / "reports/incidents.md").read_text(encoding="utf-8")
        self.assertEqual(report["statistics"]["analyzed_errors"], 7)
        self.assertEqual(markdown, render_markdown(report))
        self.assertIn("Ошибок: 7; групп: 4; гипотез: 2", result.stdout)

    def test_surrogates_in_warnings_do_not_prevent_reports(self):
        content = (json.dumps(event(level="\ud800")) + "\n"
                   + '{"ключ\\udfff":1,"ключ\\udfff":2}\n'
                   + encoded(event(service="база", reason="Сбой 🌍")).getvalue().decode("utf-8"))
        result = self.run_cli("-", input=content)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr.count("Предупреждение:"), 2)
        self.assertNotIn("Traceback", result.stderr)
        report = json.loads((self.workdir / "reports/incidents.json").read_text(encoding="utf-8"))
        markdown = (self.workdir / "reports/incidents.md").read_text(encoding="utf-8")
        self.assertEqual(report["statistics"]["invalid_lines"], 2)
        self.assertEqual(report["statistics"]["analyzed_errors"], 1)
        self.assertEqual(report["warnings"], [
            {"line": 1, "kind": "invalid_line", "message": "неизвестный уровень level: \\ud800"},
            {"line": 2, "kind": "invalid_line", "message": "повторяющийся JSON-ключ: ключ\\udfff"},
        ])
        self.assertEqual(report["facts"]["events"][0]["service"], "база")
        self.assertEqual(report["facts"]["events"][0]["reason"], "Сбой 🌍")
        self.assertIn("Сбой 🌍", markdown)
        for escaped in (r"\\ud800", r"\\udfff"):
            self.assertIn(escaped, result.stderr)
            self.assertIn(escaped, markdown)

    def test_stdin_custom_paths_and_period(self):
        result = self.run_cli("-", "--json-report", "out/result.json", "--markdown-report", "out/result.md",
                              "--since", "2026-09-19T12:00:00+03:00", "--until", "2026-09-19T09:00:00Z",
                              input=encoded(event()).getvalue().decode("utf-8"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue((self.workdir / "out/result.md").exists())
        self.assertEqual(json.loads((self.workdir / "out/result.json").read_text())["statistics"]["analyzed_errors"], 1)

    def test_empty_and_all_invalid_files_still_create_reports(self):
        for content, invalid in [("", 0), ("{broken}\nnull\n", 2)]:
            with self.subTest(content=content):
                result = self.run_cli("-", input=content)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads((self.workdir / "reports/incidents.json").read_text())
                self.assertEqual(report["statistics"]["analyzed_errors"], 0)
                self.assertEqual(report["statistics"]["invalid_lines"], invalid)

    def test_bad_arguments_missing_file_and_io_failure(self):
        for args in [("missing.jsonl",), (SAMPLE, "--window-seconds", "-1"),
                     (SAMPLE, "--window-seconds", "86401"), (SAMPLE, "--window-seconds", "x"),
                     (SAMPLE, "--since", "2026-09-19T09:00:00"),
                     (SAMPLE, "--since", "2026-09-20T00:00:00Z", "--until", "2026-09-19T00:00:00Z"),
                     (SAMPLE, "--json-report", self.workdir)]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertTrue(result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_output_cannot_overwrite_input_or_other_report(self):
        source = self.workdir / "source.jsonl"
        content = encoded(event()).getvalue()
        source.write_bytes(content)
        for args in [(source, "--json-report", source),
                     (source, "--markdown-report", source),
                     (source, "--json-report", "same", "--markdown-report", "./same")]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(source.read_bytes(), content)
        alias = self.workdir / "source-link"
        os.link(source, alias)
        result = self.run_cli(source, "--json-report", alias)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(source.read_bytes(), content)

    def test_failed_staging_preserves_previous_report(self):
        json_path = self.workdir / "existing.json"
        json_path.write_text("previous report", encoding="utf-8")
        result = self.run_cli(SAMPLE, "--json-report", json_path, "--markdown-report", self.workdir)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json_path.read_text(), "previous report")
        self.assertEqual(sorted(path.name for path in self.workdir.iterdir()), ["existing.json"])


if __name__ == "__main__":
    unittest.main()
