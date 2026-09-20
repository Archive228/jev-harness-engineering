#!/usr/bin/env python3
"""Анализ JSONL-инцидентов; только стандартная библиотека Python 3.9+."""

import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Optional


ERROR_LEVELS = {"ERROR", "CRITICAL", "FATAL"}
LEVELS = ERROR_LEVELS | {"DEBUG", "INFO", "WARNING"}
TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
)


def parse_timestamp(value):
    """Строгое ISO 8601 с явным смещением, результат всегда в UTC."""
    if not isinstance(value, str) or not TIMESTAMP_PATTERN.fullmatch(value):
        raise ValueError("timestamp должен содержать дату, время и часовой пояс (Z или ±HH:MM)")
    if value[-6:-5] in {"+", "-"}:
        if int(value[-5:-3]) > 23 or int(value[-2:]) > 59 or value.endswith("-00:00"):
            raise ValueError("недопустимое или неизвестное смещение часового пояса")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("недопустимая дата или время timestamp") from exc


def utc_text(value):
    return value.isoformat().replace("+00:00", "Z")


def required_text(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("поле %s должно быть непустой строкой" % key)
    return value.strip()


def reason_key(reason):
    return " ".join(reason.split()).casefold()


@dataclass(frozen=True)
class Event:
    event_id: str
    timestamp: datetime
    service: str
    level: str
    reason: str
    trace_id: Optional[str] = None
    upstream_service: Optional[str] = None

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("строка должна содержать JSON-объект")
        level = required_text(data, "level").upper()
        if level == "WARN":
            level = "WARNING"
        if level not in LEVELS:
            raise ValueError("неизвестный уровень level: %s" % level)
        return cls(
            event_id=required_text(data, "event_id"),
            timestamp=parse_timestamp(data.get("timestamp")),
            service=required_text(data, "service"),
            level=level,
            reason=required_text(data, "reason"),
            trace_id=required_text(data, "trace_id") if "trace_id" in data else None,
            upstream_service=(required_text(data, "upstream_service")
                              if "upstream_service" in data else None),
        )

    def as_dict(self):
        result = {
            "event_id": self.event_id,
            "timestamp": utc_text(self.timestamp),
            "service": self.service,
            "level": self.level,
            "reason": self.reason,
        }
        if self.trace_id is not None:
            result["trace_id"] = self.trace_id
        if self.upstream_service is not None:
            result["upstream_service"] = self.upstream_service
        return result


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("повторяющийся JSON-ключ: %s" % key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("недопустимая JSON-константа: %s" % value)


def read_events(lines):
    """Первое валидное событие с данным ID побеждает до фильтрации."""
    events, warnings = {}, []
    stats = dict(total_lines=0, blank_lines=0, invalid_lines=0,
                 duplicate_events=0, conflicting_duplicates=0, unique_events=0)
    for line_number, raw_line in enumerate(lines, 1):
        stats["total_lines"] += 1
        try:
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if line_number == 1:
                line = line.removeprefix("\ufeff")
            if not line.strip():
                stats["blank_lines"] += 1
                continue
            data = json.loads(line, object_pairs_hook=unique_json_object,
                              parse_constant=reject_constant)
            event = Event.from_dict(data)
            # JSON допускает экранированные одиночные суррогаты, UTF-8 — нет.
            for value in event.as_dict().values():
                value.encode("utf-8")
        except (ValueError, UnicodeError, RecursionError) as exc:
            stats["invalid_lines"] += 1
            # Текст ошибки тоже может содержать одиночные JSON-суррогаты.
            message = str(exc).encode("utf-8", errors="backslashreplace").decode("utf-8")
            warnings.append({"line": line_number, "kind": "invalid_line", "message": message})
            continue
        previous = events.get(event.event_id)
        if previous is not None:
            stats["duplicate_events"] += 1
            if previous != event:
                stats["conflicting_duplicates"] += 1
                warnings.append({
                    "line": line_number, "kind": "conflicting_duplicate",
                    "event_id": event.event_id,
                    "message": "конфликтующий дубль event_id=%s; сохранена первая валидная запись"
                               % event.event_id,
                })
            continue
        events[event.event_id] = event
    stats["unique_events"] = len(events)
    return sorted(events.values(), key=lambda event: (event.timestamp, event.event_id)), stats, warnings


def group_errors(events):
    buckets = defaultdict(list)
    for event in events:
        buckets[(event.service, reason_key(event.reason))].append(event)
    return [
        {"service": service, "reason": reason, "count": len(group),
         "first_seen": utc_text(group[0].timestamp), "last_seen": utc_text(group[-1].timestamp),
         "event_ids": [event.event_id for event in group]}
        for (service, reason), group in sorted(buckets.items())
    ]


def infer_hypotheses(events, window_seconds):
    """Совпавшие trace + upstream + время дают гипотезу, но не причинность."""
    by_trace_service = defaultdict(list)
    for event in events:
        if event.trace_id:
            by_trace_service[(event.trace_id, event.service)].append(event)
    times = {key: [event.timestamp for event in group]
             for key, group in by_trace_service.items()}
    candidates = defaultdict(list)
    for downstream in events:
        if not downstream.trace_id or not downstream.upstream_service:
            continue
        if downstream.upstream_service == downstream.service:
            continue
        key = (downstream.trace_id, downstream.upstream_service)
        group = by_trace_service.get(key, [])
        timestamps = times.get(key, [])
        try:
            earliest = downstream.timestamp - timedelta(seconds=window_seconds)
        except OverflowError:
            earliest = datetime.min.replace(tzinfo=timezone.utc)
        start = bisect_left(timestamps, earliest)
        end = bisect_right(timestamps, downstream.timestamp)
        for upstream in group[start:end]:
            cause_key = (upstream.service, reason_key(upstream.reason),
                         downstream.service, reason_key(downstream.reason))
            candidates[cause_key].append({
                "upstream_event_id": upstream.event_id,
                "downstream_event_id": downstream.event_id,
                "trace_id": downstream.trace_id,
                "delay_seconds": (downstream.timestamp - upstream.timestamp).total_seconds(),
            })
    hypotheses = []
    for number, (key, links) in enumerate(sorted(candidates.items()), 1):
        upstream_service, upstream_reason, downstream_service, downstream_reason = key
        evidence = {link[field] for link in links
                    for field in ("upstream_event_id", "downstream_event_id")}
        hypotheses.append({
            "id": "H%03d" % number,
            "status": "hypothesis",
            "upstream_service": upstream_service, "upstream_reason": upstream_reason,
            "downstream_service": downstream_service, "downstream_reason": downstream_reason,
            "statement": "Сбой %s (%s) мог способствовать сбою %s (%s)."
                         % (upstream_service, upstream_reason, downstream_service, downstream_reason),
            "evidence_event_ids": [event.event_id for event in events if event.event_id in evidence],
            "observed_links": links,
            "limitations": [
                "Совпали trace_id, заявленный upstream_service и временное окно; причинность не доказана.",
                "Порядок основан на часах источников; рассинхронизация часов и общая внешняя причина не исключены.",
            ],
            "verification_steps": [
                "Проверить spans этой трассы и фактический вызов upstream-сервиса.",
                "Сопоставить метрики и журналы upstream-сервиса, проверить альтернативные причины.",
            ],
        })
    return hypotheses


def analyze(lines, source="<stream>", window_seconds=120, since=None, until=None):
    if not isinstance(window_seconds, int) or isinstance(window_seconds, bool) or not 0 <= window_seconds <= 86400:
        raise ValueError("window_seconds должен быть целым числом от 0 до 86400")
    for bound in (since, until):
        if bound is not None and (bound.tzinfo is None or bound.utcoffset() is None):
            raise ValueError("границы периода должны содержать часовой пояс")
    if since is not None and until is not None and since > until:
        raise ValueError("since должен быть не позднее until")
    events, stats, warnings = read_events(lines)
    in_period = [event for event in events
                 if (since is None or event.timestamp >= since) and (until is None or event.timestamp <= until)]
    errors = [event for event in in_period if event.level in ERROR_LEVELS]
    stats.update(events_outside_period=len(events) - len(in_period),
                 non_error_events_in_period=len(in_period) - len(errors), analyzed_errors=len(errors))
    hypotheses = infer_hypotheses(errors, window_seconds)
    linked_ids = {event_id for hypothesis in hypotheses for event_id in hypothesis["evidence_event_ids"]}
    return {
        "schema_version": 1,
        "source": source,
        "settings": {"window_seconds": window_seconds,
                     "since": utc_text(since.astimezone(timezone.utc)) if since else None,
                     "until": utc_text(until.astimezone(timezone.utc)) if until else None},
        "statistics": stats,
        "warnings": warnings,
        "facts": {
            "scope": "Наблюдения из принятых записей журнала; достоверность источника отдельно не проверялась.",
            "events": [event.as_dict() for event in errors],
            "groups": group_errors(errors),
            "unlinked_event_ids": [event.event_id for event in errors if event.event_id not in linked_ids],
        },
        "hypotheses": hypotheses,
        "root_cause": {"established": False,
                       "explanation": "Первопричина не доказана: диагностическая причина в логе и корреляция не устанавливают причинность."},
    }


def md(value):
    """Не позволять тексту журналов изменять структуру Markdown/HTML."""
    value = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value = " ".join(value.split())
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", value)


def render_markdown(report):
    stats = report["statistics"]
    lines = ["# Отчёт об инцидентах", "", "Источник: " + md(report["source"]), "",
             "## Факты из журнала", "", report["facts"]["scope"], "",
             "- Строк: %d; пустых: %d; битых: %d." %
             (stats["total_lines"], stats["blank_lines"], stats["invalid_lines"]),
             "- Уникальных событий: %d; дублей: %d, из них конфликтующих: %d." %
             (stats["unique_events"], stats["duplicate_events"], stats["conflicting_duplicates"]),
             "- Ошибок в периоде: %d; прочих событий в периоде: %d; вне периода: %d." %
             (stats["analyzed_errors"], stats["non_error_events_in_period"], stats["events_outside_period"]), "",
             "Время приведено к UTC. Границы периода включены. Окно связи: %d с." % report["settings"]["window_seconds"],
             "Период: %s — %s." % (report["settings"]["since"] or "без нижней границы",
                                   report["settings"]["until"] or "без верхней границы"), "",
             "### Группы ошибок по сервису и причине", "",
             "Причина здесь — текст диагностики из лога, а не доказанная первопричина.", ""]
    for group in report["facts"]["groups"]:
        lines.extend(["- **%s / %s**: %d; %s — %s. event_id: %s." %
                      (md(group["service"]), md(group["reason"]), group["count"],
                       group["first_seen"], group["last_seen"], ", ".join(map(md, group["event_ids"])))])
    if not report["facts"]["groups"]:
        lines.append("Ошибок нет.")
    lines.extend(["", "### Хронология принятых ошибок", ""])
    for event in report["facts"]["events"]:
        lines.append("- %s — event_id: %s; сервис: %s; %s; причина: %s; trace_id: %s; upstream_service: %s." %
                     (event["timestamp"], md(event["event_id"]), md(event["service"]), md(event["level"]),
                      md(event["reason"]), md(event.get("trace_id", "—")), md(event.get("upstream_service", "—"))))
    lines.extend(["", "## Гипотезы о причине", "", "**Первопричина не доказана.**", "",
                  report["root_cause"]["explanation"], ""])
    for hypothesis in report["hypotheses"]:
        lines.extend(["### %s — гипотеза" % hypothesis["id"], "", md(hypothesis["statement"]), "",
                      "event_id доказательств наблюдаемой связи: " + ", ".join(map(md, hypothesis["evidence_event_ids"])), ""])
        for link in hypothesis["observed_links"]:
            lines.append("- %s → %s; trace_id: %s; задержка по журналу: %g с." %
                         (md(link["upstream_event_id"]), md(link["downstream_event_id"]),
                          md(link["trace_id"]), link["delay_seconds"]))
        lines.extend([""] + hypothesis["limitations"] + ["", "Проверки:", ""])
        lines.extend("- " + step for step in hypothesis["verification_steps"])
        lines.append("")
    if not report["hypotheses"]:
        lines.extend(["Недостаточно данных для гипотез по выбранным правилам.", ""])
    lines.extend(["## Ошибки без достаточных данных для связи", "",
                  "event_id: " + (", ".join(map(md, report["facts"]["unlinked_event_ids"])) or "нет"), "",
                  "Это не доказательство независимости. Близость по времени сама по себе не связывает события.", "",
                  "## Предупреждения чтения", ""])
    for warning in report["warnings"]:
        lines.append("- Строка %d: %s." % (warning["line"], md(warning["message"])))
    if not report["warnings"]:
        lines.append("Нет.")
    return "\n".join(lines) + "\n"


def write_reports(report, json_path, markdown_path):
    """Подготовить оба файла; заменить каждый через атомарный os.replace."""
    contents = [(json_path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"),
                (markdown_path, render_markdown(report))]
    staged = []
    try:
        for target, content in contents:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir():
                raise OSError("путь отчёта является каталогом: %s" % target)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=target.parent, delete=False) as handle:
                staged.append((Path(handle.name), target))
                handle.write(content)
        for temporary, target in staged:
            os.replace(str(temporary), str(target))
    finally:
        for temporary, _ in staged:
            if temporary.exists():
                temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSONL в UTF-8 или - для stdin")
    parser.add_argument("--json-report", type=Path, default=Path("reports/incidents.json"))
    parser.add_argument("--markdown-report", type=Path, default=Path("reports/incidents.md"))
    parser.add_argument("--window-seconds", type=int, default=120, help="окно связи 0..86400 секунд (по умолчанию 120)")
    parser.add_argument("--since", type=parse_timestamp, help="включительная нижняя граница ISO 8601 с часовым поясом")
    parser.add_argument("--until", type=parse_timestamp, help="включительная верхняя граница ISO 8601 с часовым поясом")
    args = parser.parse_args(argv)
    try:
        outputs = [args.json_report.resolve(), args.markdown_report.resolve()]
        if outputs[0] == outputs[1] or (outputs[0].exists() and outputs[1].exists() and outputs[0].samefile(outputs[1])):
            raise ValueError("JSON- и Markdown-отчёты должны иметь разные пути")
        if args.input != "-":
            source = Path(args.input).resolve()
            if any(source == output or (source.exists() and output.exists() and source.samefile(output))
                   for output in outputs):
                raise ValueError("путь отчёта совпадает с входным файлом")
        stream = nullcontext(sys.stdin.buffer) if args.input == "-" else open(args.input, "rb")
        with stream as lines:
            report = analyze(lines, args.input, args.window_seconds, args.since, args.until)
        for warning in report["warnings"]:
            print("Предупреждение: строка %d: %s" % (warning["line"], md(warning["message"])), file=sys.stderr)
        write_reports(report, *outputs)
    except (OSError, ValueError) as exc:
        print("Ошибка: %s" % exc, file=sys.stderr)
        return 2
    print("Ошибок: %d; групп: %d; гипотез: %d. JSON: %s; Markdown: %s" %
          (report["statistics"]["analyzed_errors"], len(report["facts"]["groups"]),
           len(report["hypotheses"]), args.json_report, args.markdown_report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
