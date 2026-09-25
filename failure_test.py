#!/usr/bin/env python3
"""Measure service behavior while one BARQ application replica is stopped."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
APP_SERVICE = re.compile(r"app-\d+$")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class FailureTestError(RuntimeError):
    """A failed assertion or bounded operation in the failure test."""


def run(command: list[str], timeout: int = 20) -> str:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FailureTestError(f"could not run {' '.join(command[:2])}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1] if detail else f"exit {result.returncode}"
        raise FailureTestError(f"{' '.join(command)} failed: {message}")
    return result.stdout.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FailureTestError(message)


def find_target(project: str, service: str) -> tuple[str, dict]:
    container_ids = run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        ]
    ).splitlines()
    require(len(container_ids) == 1, f"expected one {project}/{service} container, found {len(container_ids)}")
    container = json.loads(run(["docker", "inspect", container_ids[0]]))[0]
    labels = container.get("Config", {}).get("Labels", {}) or {}
    require(labels.get("com.docker.compose.project") == project, "target Compose project label does not match")
    require(labels.get("com.docker.compose.service") == service, "target Compose service label does not match")
    return container_ids[0], container


def container_state(container_id: str) -> dict:
    return json.loads(run(["docker", "inspect", container_id]))[0].get("State", {})


def wait_for_state(container_id: str, *, running: bool, healthy: bool | None, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    last_state = "unknown"
    while time.monotonic() < deadline:
        state = container_state(container_id)
        is_running = state.get("Running") is True
        health = state.get("Health", {}).get("Status")
        last_state = f"running={is_running}, health={health or 'not configured'}"
        if is_running == running and (healthy is None or (health == "healthy") == healthy):
            return
        time.sleep(1)
    raise FailureTestError(f"container state timed out after {timeout}s ({last_state})")


def request_instance(base_url: str) -> tuple[bool, str]:
    request = Request(
        base_url.rstrip("/") + "/instance",
        headers={"X-Request-ID": f"failure-test-{uuid.uuid4().hex}"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if response.status != 200:
                return False, f"HTTP {response.status}"
            identity = payload.get("instance_id")
            if not isinstance(identity, str):
                return False, "invalid JSON identity"
            return True, identity
    except HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, type(exc).__name__


def measure(base_url: str, count: int) -> tuple[Counter, Counter, float]:
    successes: Counter = Counter()
    errors: Counter = Counter()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(10, count)) as executor:
        results = executor.map(lambda _: request_instance(base_url), range(count))
    for ok, result in results:
        (successes if ok else errors)[result] += 1
    return successes, errors, time.monotonic() - started


def format_counts(counts: Counter) -> str:
    return ", ".join(f"{name}={count}" for name, count in sorted(counts.items())) or "none"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stop one BARQ backend and prove recovery")
    parser.add_argument("--project", default="barq-assessment", help="Compose project label to target")
    parser.add_argument("--service", default="app-01", help="application service to stop")
    parser.add_argument("--url", default="http://127.0.0.1:8090", help="public loopback URL")
    parser.add_argument("--requests", type=int, default=60, help="requests to send during the failure")
    parser.add_argument("--recovery-timeout", type=int, default=45, help="seconds to wait for healthy recovery")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS or parsed.path not in ("", "/"):
        print("FAIL: --url must be an HTTP loopback origin without a path", file=sys.stderr)
        return 1
    if APP_SERVICE.fullmatch(args.service) is None:
        print("FAIL: --service must use the app-NN naming pattern", file=sys.stderr)
        return 1
    if not 2 <= args.requests <= 500:
        print("FAIL: --requests must be between 2 and 500", file=sys.stderr)
        return 1
    if not 5 <= args.recovery_timeout <= 300:
        print("FAIL: --recovery-timeout must be between 5 and 300 seconds", file=sys.stderr)
        return 1

    restore_required = False
    target_id = ""
    failure: Exception | None = None
    try:
        target_id, target = find_target(args.project, args.service)
        initial_state = target.get("State", {})
        require(initial_state.get("Running") is True, f"{args.service} is not running before the test")
        require(
            initial_state.get("Health", {}).get("Status") == "healthy",
            f"{args.service} is not healthy before the test",
        )
        baseline_successes, baseline_errors, _ = measure(args.url, 4)
        require(sum(baseline_successes.values()) == 4 and not baseline_errors, "public endpoint is not healthy before the test")
        print(f"PASS: preflight succeeded; stopping {args.project}/{args.service}")

        restore_required = True
        run(["docker", "stop", "--time", "10", target_id])
        wait_for_state(target_id, running=False, healthy=None, timeout=15)
        print(f"PASS: {args.service} is stopped")

        failure_successes, failure_errors, duration = measure(args.url, args.requests)
        success_count = sum(failure_successes.values())
        error_count = sum(failure_errors.values())
        availability = success_count / args.requests * 100
        print(
            f"MEASURE: during failure requests={args.requests}, successes={success_count}, "
            f"errors={error_count}, availability={availability:.1f}%, duration={duration:.2f}s"
        )
        print(f"MEASURE: successful instances: {format_counts(failure_successes)}")
        print(f"MEASURE: error types: {format_counts(failure_errors)}")
        require(success_count > 0, "no requests succeeded while one backend was stopped")
        require(error_count > 0, "no proxy errors were observed while one backend was stopped")
        require(args.service not in failure_successes, "the stopped backend unexpectedly served a request")
        print("PASS: surviving backend continued serving while proxy errors remained visible")
    except (FailureTestError, KeyboardInterrupt) as exc:
        failure = exc
    finally:
        if restore_required and target_id:
            try:
                run(["docker", "start", target_id])
                wait_for_state(
                    target_id,
                    running=True,
                    healthy=True,
                    timeout=args.recovery_timeout,
                )
                print(f"PASS: {args.service} restarted and became healthy")
            except FailureTestError as restore_error:
                if failure is None:
                    failure = restore_error
                else:
                    failure = FailureTestError(f"{failure}; restoration also failed: {restore_error}")

    if failure is not None:
        print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    recovery_successes: Counter = Counter()
    recovery_errors: Counter = Counter()
    for _ in range(max(64, args.requests)):
        ok, result = request_instance(args.url)
        (recovery_successes if ok else recovery_errors)[result] += 1
        if result == args.service:
            break
    require_recovered = args.service in recovery_successes
    if not require_recovered:
        print(
            f"FAIL: recovered {args.service} did not serve traffic; "
            f"successes: {format_counts(recovery_successes)}; errors: {format_counts(recovery_errors)}",
            file=sys.stderr,
        )
        return 1
    print(f"PASS: recovered backend served a request ({format_counts(recovery_successes)})")
    print("PASS: failure and recovery test completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
