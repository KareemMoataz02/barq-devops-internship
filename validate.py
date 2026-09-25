#!/usr/bin/env python3
"""Validate the running BARQ Compose environment without changing its topology."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
APP_SERVICE = re.compile(r"app-\d+$")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ValidationError(RuntimeError):
    """A failed validation with a message suitable for the terminal."""


def run(command: list[str], timeout: int = 15) -> str:
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
        raise ValidationError(f"could not run {' '.join(command[:2])}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1] if detail else f"exit {result.returncode}"
        raise ValidationError(f"{' '.join(command)} failed: {message}")
    return result.stdout.strip()


def passed(message: str) -> None:
    print(f"PASS: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def inspect_project(project: str) -> dict[str, dict]:
    container_ids = run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ]
    ).splitlines()
    require(bool(container_ids), f"no containers found for Compose project {project!r}")
    containers = json.loads(run(["docker", "inspect", *container_ids]))
    services: dict[str, dict] = {}
    for container in containers:
        labels = container.get("Config", {}).get("Labels", {}) or {}
        service = labels.get("com.docker.compose.service")
        require(bool(service), f"container {container.get('Name', '').lstrip('/')} has no Compose service label")
        require(service not in services, f"Compose project has multiple containers for service {service}")
        services[service] = container
    return services


def validate_runtime(project: str, expected_port: int) -> set[str]:
    services = inspect_project(project)
    required = {"nginx", "postgres", "redis", "app-01", "app-02"}
    require(required <= services.keys(), f"missing services: {', '.join(sorted(required - services.keys()))}")
    apps = {name for name in services if APP_SERVICE.fullmatch(name)}
    require(len(apps) >= 2, "at least two application replicas are required")

    for service in sorted(required | apps):
        state = services[service].get("State", {})
        require(state.get("Running") is True, f"{service} is not running")
        health = state.get("Health", {}).get("Status")
        require(health == "healthy", f"{service} health is {health or 'not configured'}")
    passed(f"{len(required | apps)} required containers are running and healthy")

    network_sets = {
        service: set(container.get("NetworkSettings", {}).get("Networks", {}))
        for service, container in services.items()
    }
    frontend = {name for name in network_sets["nginx"] if name.endswith("_frontend") or name == "frontend"}
    backend = {name for name in network_sets["postgres"] if name.endswith("_backend") or name == "backend"}
    require(len(frontend) == 1, "could not identify exactly one frontend network")
    require(len(backend) == 1, "could not identify exactly one backend network")
    frontend_name = next(iter(frontend))
    backend_name = next(iter(backend))
    require(network_sets["nginx"] == {frontend_name}, "nginx must connect only to the frontend network")
    for service in apps:
        require(
            network_sets[service] == {frontend_name, backend_name},
            f"{service} must connect to the frontend and backend networks",
        )
    for service in ("postgres", "redis"):
        require(network_sets[service] == {backend_name}, f"{service} must connect only to the backend network")
    backend_details = json.loads(run(["docker", "network", "inspect", backend_name]))[0]
    require(backend_details.get("Internal") is True, "backend network is not internal")
    passed("frontend and internal backend network isolation is correct")

    for service, container in services.items():
        bindings = container.get("NetworkSettings", {}).get("Ports", {}) or {}
        published = [(port, item) for port, items in bindings.items() for item in (items or [])]
        if service == "nginx":
            require(len(published) == 1, "nginx must have exactly one published port")
            container_port, binding = published[0]
            require(container_port == "80/tcp", f"nginx publishes unexpected container port {container_port}")
            require(binding.get("HostIp") in {"127.0.0.1", "::1"}, "nginx port is not bound to loopback")
            require(binding.get("HostPort") == str(expected_port), "nginx host port does not match the validation URL")
        else:
            require(not published, f"{service} must not publish a host port")
    passed(f"only nginx publishes loopback port {expected_port}")
    return apps


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    expected_status: int = 200,
) -> tuple[dict, dict[str, str]]:
    request_id = f"validate-{uuid.uuid4().hex}"
    headers = {"X-Request-ID": request_id}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            status = response.status
            headers = {name.lower(): value for name, value in response.headers.items()}
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ValidationError(f"{method} {path} returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{method} {path} failed: {exc}") from exc
    require(status == expected_status, f"{method} {path} returned HTTP {status}")
    returned_request_id = headers.get("x-request-id", "")
    require(
        re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", returned_request_id) is not None,
        f"{method} {path} did not return a valid request ID",
    )
    require(
        headers.get("x-instance-id") == payload.get("instance_id"),
        f"{method} {path} has inconsistent instance identity",
    )
    return payload, headers


def get_json(base_url: str, path: str) -> tuple[dict, dict[str, str]]:
    return request_json(base_url, path)


def validate_http(base_url: str, apps: set[str]) -> None:
    root, _ = get_json(base_url, "/")
    require(root.get("service") == "barq-api" and bool(root.get("message")), "root response is incomplete")

    health, _ = get_json(base_url, "/health")
    require(health.get("status") == "alive", "health endpoint did not report alive")

    ready, _ = get_json(base_url, "/ready")
    require(ready.get("status") == "ready", "readiness endpoint did not report ready")
    require(ready.get("dependencies") == {"postgres": "ready", "redis": "ready"}, "dependencies are not ready")

    title = f"validation-{uuid.uuid4().hex[:12]}"
    created, _ = request_json(
        base_url,
        "/records",
        method="POST",
        body={"title": title},
        expected_status=201,
    )
    created_record = created.get("record")
    require(isinstance(created_record, dict) and created_record.get("title") == title, "record creation failed")
    records, _ = get_json(base_url, "/records")
    record_list = records.get("records")
    require(isinstance(record_list, list), "records endpoint did not return a list")
    require(created_record in record_list, "new PostgreSQL record was not returned by the list endpoint")

    first_counter, _ = get_json(base_url, "/counter")
    second_counter, _ = get_json(base_url, "/counter")
    first_value = first_counter.get("counter")
    second_value = second_counter.get("counter")
    require(isinstance(first_value, int) and second_value == first_value + 1, "Redis counter did not increment by one")
    passed("public endpoints, PostgreSQL records, and Redis counter are working")

    seen: set[str] = set()
    for _ in range(max(64, len(apps) * 32)):
        payload, _ = get_json(base_url, "/instance")
        identity = payload.get("instance_id")
        require(identity in apps, f"unexpected backend identity {identity!r}")
        seen.add(identity)
        if seen == apps:
            break
    require(seen == apps, f"load balancer did not reach: {', '.join(sorted(apps - seen))}")
    passed(f"load balancer reached every backend: {', '.join(sorted(seen))}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a running BARQ Compose project")
    parser.add_argument("--project", default="barq-assessment", help="Compose project label to inspect")
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="public loopback URL")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS or parsed.path not in ("", "/"):
        print("FAIL: --url must be an HTTP loopback origin without a path", file=sys.stderr)
        return 1
    expected_port = parsed.port or 80
    try:
        run(["docker", "compose", "config", "--quiet"])
        passed("Compose configuration is valid")
        apps = validate_runtime(args.project, expected_port)
        validate_http(args.url.rstrip("/"), apps)
    except ValidationError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("PASS: BARQ environment validation completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
