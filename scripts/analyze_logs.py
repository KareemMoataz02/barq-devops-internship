#!/usr/bin/env python3
"""Reproduce the counts used in log_analysis.md from the supplied logs."""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


ERROR_LINE = re.compile(r"^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} \[(?:error|notice)\] .+$")


@dataclass
class ParsedLog:
    physical: int
    valid: list[dict | str]
    unique: list[dict | str]
    malformed: list[int]
    duplicate_groups: int
    duplicate_extras: int


def parse_log(path: Path, *, json_lines: bool) -> ParsedLog:
    lines = path.read_text(encoding="utf-8").splitlines()
    valid: list[dict | str] = []
    valid_text: list[str] = []
    unique: list[dict | str] = []
    seen: set[str] = set()
    malformed: list[int] = []
    for line_number, line in enumerate(lines, 1):
        try:
            parsed = json.loads(line) if json_lines else line
            if not json_lines and ERROR_LINE.fullmatch(line) is None:
                raise ValueError("unrecognized error-log line")
        except (json.JSONDecodeError, ValueError):
            malformed.append(line_number)
            continue
        valid.append(parsed)
        valid_text.append(line)
        if line not in seen:
            seen.add(line)
            unique.append(parsed)
    frequencies = Counter(valid_text)
    return ParsedLog(
        physical=len(lines),
        valid=valid,
        unique=unique,
        malformed=malformed,
        duplicate_groups=sum(count > 1 for count in frequencies.values()),
        duplicate_extras=sum(count - 1 for count in frequencies.values() if count > 1),
    )


def counter_text(counter: Counter) -> str:
    return ", ".join(f"{key}={counter[key]}" for key in sorted(counter, key=str))


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze the three supplied BARQ logs")
    parser.add_argument("--logs", type=Path, default=Path("logs"), help="directory containing the logs")
    args = parser.parse_args()

    access_log = parse_log(args.logs / "access.log", json_lines=True)
    error_log = parse_log(args.logs / "error.log", json_lines=False)
    application_log = parse_log(args.logs / "application.log", json_lines=True)

    print("FILE QUALITY (valid includes duplicate physical lines)")
    for name, parsed in (
        ("access.log", access_log),
        ("error.log", error_log),
        ("application.log", application_log),
    ):
        print(
            f"{name}: physical={parsed.physical} valid={len(parsed.valid)} "
            f"malformed={len(parsed.malformed)} duplicate_extras={parsed.duplicate_extras} "
            f"duplicate_groups={parsed.duplicate_groups} malformed_lines={parsed.malformed or 'none'}"
        )

    access = [row for row in access_log.unique if isinstance(row, dict)]
    application = [row for row in application_log.unique if isinstance(row, dict)]
    errors = [row for row in error_log.unique if isinstance(row, str)]

    access_by_id: dict[str, list[dict]] = defaultdict(list)
    for row in access:
        access_by_id[row["request_id"]].append(row)
    conflicting_ids = {request_id: rows for request_id, rows in access_by_id.items() if len(rows) != 1}
    if conflicting_ids:
        raise RuntimeError(f"access log has conflicting rows for request IDs: {sorted(conflicting_ids)}")
    requests = [rows[0] for rows in access_by_id.values()]

    combined_end = max(
        max(row["timestamp"] for row in access),
        max(row["timestamp"] for row in application),
        max(row[:10].replace("/", "-") + "T" + row[11:19] + "Z" for row in errors),
    )
    print("\nINTERVAL")
    print(f"combined_start={min(row['timestamp'] for row in access)} combined_end={combined_end}")
    print(f"access_and_application_end={max(row['timestamp'] for row in access)}")

    statuses = Counter(row["status"] for row in requests)
    server_errors = sum(count for status, count in statuses.items() if status >= 500)
    non_2xx = sum(count for status, count in statuses.items() if not 200 <= status < 300)
    print("\nCLIENT OUTCOMES")
    print(f"distinct_requests={len(requests)}")
    print(f"final_statuses: {counter_text(statuses)}")
    print(f"server_error_rate={server_errors}/{len(requests)}={server_errors / len(requests) * 100:.2f}%")
    print(f"non_2xx_rate={non_2xx}/{len(requests)}={non_2xx / len(requests) * 100:.2f}%")

    latencies = sorted(float(row["request_time"]) for row in requests)
    median = statistics.median(latencies)
    p95 = latencies[math.ceil(0.95 * len(latencies)) - 1]
    print("\nLATENCY (all distinct client requests)")
    print(f"median_ms={median * 1000:.0f} p95_nearest_rank_ms={p95 * 1000:.0f}")

    retries = [row for row in requests if "," in str(row.get("upstream_status", ""))]
    retry_successes = [row for row in retries if row["status"] < 500]
    print("\nRETRIES")
    print(f"retried_requests={len(retries)} successful_after_retry={len(retry_successes)}")
    print("request_ids=" + ",".join(row["request_id"] for row in retries))

    failures = [row for row in requests if row["status"] >= 500]
    print("\nFAILURE DISTRIBUTION")
    print("by_path_status: " + counter_text(Counter((row["path"], row["status"]) for row in failures)))
    print("by_upstream_status: " + counter_text(Counter((row["upstream"], row["status"]) for row in failures)))

    error_types = Counter()
    for line in errors:
        if "connect() failed" in line:
            error_types["connection_refused"] += 1
        elif "upstream timed out" in line:
            error_types["upstream_timeout"] += 1
        elif "[notice]" in line:
            error_types["notice"] += 1
        else:
            error_types["other"] += 1
    print("\nERROR LOG")
    print(counter_text(error_types))

    dependency_errors = [row for row in application if row.get("event") == "dependency_error"]
    print("\nAPPLICATION DEPENDENCY ERRORS")
    print(
        "by_dependency_error: "
        + counter_text(Counter((row["dependency"], row["error_type"]) for row in dependency_errors))
    )
    print("by_instance: " + counter_text(Counter(row["instance_id"] for row in dependency_errors)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
