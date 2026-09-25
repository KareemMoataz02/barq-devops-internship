# Technical decisions and trade-offs

This record describes the final Compose design and distinguishes choices implemented in
the repository from improvements that would require a production platform. The lab runs
on one Docker host, uses synthetic data, and is intended for local assessment rather than
internet-facing production traffic.

## 1. Use a small, pinned Python runtime and a production WSGI server

- **Choice:** Build the application from the digest-pinned `python:3.12-slim-bookworm`
  image and run it with Gunicorn as UID/GID 10001. Gunicorn uses two workers, two threads
  per worker, and a 30-second worker timeout.
- **Why:** The slim Debian image keeps familiar package behavior while reducing the image
  compared with full Debian. Pinning the digest makes builds reproducible. Gunicorn can
  handle concurrent requests and process failures more safely than Flask's development
  server, while the fixed unprivileged identity limits the effect of an application
  compromise.
- **Alternative considered:** Alpine would be smaller, but Python packages with native
  extensions can require musl-specific builds and troubleshooting. The Flask development
  server would be simpler but is unsuitable as the runtime server.
- **Trade-off and limit:** A digest does not receive security updates automatically; it
  must be refreshed deliberately. Four request threads per replica are reasonable for
  this small I/O-bound lab, not a capacity claim. The image has no read-only root
  filesystem and has not been minimized with a multi-stage build.
- **Evidence / commit:** `e11fe0d` (`security: run apps as non-root with Gunicorn`).
- **Production improvement:** Scan images, rebuild on a scheduled patch cadence, sign the
  result, tune workers from load tests, drop Linux capabilities, and use a read-only root
  filesystem with a writable temporary mount if the application needs one.

## 2. Probe real service behavior and gate startup on health

- **Choice:** Each service has a bounded health check. Applications probe their actual
  `/health` route, PostgreSQL uses `pg_isready`, Redis uses `PING`, and NGINX calls the
  proxied health route. Compose starts applications only after both data services are
  healthy, then starts NGINX after both applications are healthy.
- **Why:** Process existence alone does not prove that a service can answer its expected
  protocol. Health-gated dependencies prevent the predictable startup race in which an
  application begins before PostgreSQL or Redis can accept requests.
- **Alternative considered:** Start all containers together and rely on application
  retries. That starts faster but shifts orchestration concerns into the application and
  makes early failures harder to interpret.
- **Trade-off and limit:** Compose dependency conditions control initial startup only;
  they do not continuously remove unhealthy services or restart their dependants. NGINX's
  health check reaches an upstream and therefore reports the end-to-end path, but it also
  means an upstream outage can make the proxy unhealthy even when NGINX itself is running.
- **Evidence / commits:** `6483864` (`fix: use the implemented application health
  endpoint`) and `b6b59c7` (`reliability: gate startup on service health`).
- **Production improvement:** Use separate liveness, readiness, and startup probes in an
  orchestrator. Readiness should remove a failing replica from service without restarting
  a healthy process, while liveness should restart only a stuck process.

## 3. Expose one loopback entry point and separate frontend from data traffic

- **Choice:** Publish only NGINX, bound to `127.0.0.1:${PUBLIC_PORT:-8080}`. NGINX and the
  applications share `frontend`; the applications, PostgreSQL, and Redis share an
  `internal: true` `backend` network. NGINX cannot join the backend network, and the data
  services publish no host ports.
- **Why:** Requests follow one controlled path: host -> NGINX:80 -> app:8080. Applications
  bridge the web and data tiers, while PostgreSQL and Redis cannot be reached directly
  from the host or proxy. Loopback binding avoids exposing the assessment service to the
  local network.
- **Alternative considered:** A single Compose network is easier to configure, but every
  service could then resolve and reach every other service. Publishing database ports
  would simplify desktop debugging at the cost of a larger attack surface.
- **Trade-off and limit:** This is network segmentation, not strong workload isolation;
  both applications still hold credentials and can reach both data services. One NGINX
  container and one Docker host remain single points of failure.
- **Evidence / commits:** `96943d8` (`fix: expose app listeners to the frontend network`)
  and `b243d59` (`security: isolate data services on the backend network`).
- **Production improvement:** Place replicas across hosts or availability zones behind a
  managed load balancer. Apply workload-level network policy, TLS at the edge and between
  services where required, and firewall rules outside the container network.

## 4. Keep proxy failure behavior measurable with bounded timeouts and no retry

- **Choice:** NGINX uses a 2-second connection timeout, a 3-second read timeout, and
  `proxy_next_upstream off`. Upstream servers use `max_fails=0`, so NGINX keeps both
  configured endpoints in rotation rather than silently excluding one based on passive
  failure counts.
- **Why:** Bounded waits prevent a failed upstream from holding a client connection
  indefinitely. Disabling retry makes the failure experiment show the availability of the
  configured round-robin design directly: when one of two replicas is stopped, requests
  assigned to it fail instead of being hidden by a second attempt.
- **Alternative considered:** Retry connection failures and idempotent requests on the
  other upstream. That would improve apparent availability but could hide a broken
  replica, amplify traffic, and risk duplicate effects if write requests were retried.
- **Trade-off and limit:** The deliberate no-retry policy caused roughly half the requests
  to fail during the one-replica failure test. The supplied logs also show requests that
  exceeded the proxy's read timeout even though the application later completed. The
  proxy timeout and Gunicorn's 30-second worker timeout are not aligned as a production
  latency budget.
- **Evidence / commits:** `3b85907` (`test: automate backend failure and recovery`) and
  `2cbe8c6` (`docs: analyze and correlate the supplied logs`).
- **Production improvement:** Define an end-to-end latency budget, add active readiness
  based routing, and retry only safe idempotent methods with a strict retry budget and
  observability. Use circuit breaking or outlier detection to stop routing to a failed
  replica.

## 5. Use automatic restart with explicit per-container resource ceilings

- **Choice:** All services use `restart: unless-stopped` and set CPU, memory, and PID
  limits. Each application gets 0.50 CPU, 256 MiB, and 128 PIDs; PostgreSQL gets 0.75 CPU,
  512 MiB, and 256 PIDs; Redis and NGINX each get 0.25 CPU, 128 MiB, and 128 PIDs.
- **Why:** The restart policy recovers from a process crash and preserves an operator's
  intentional stop. Resource limits keep one faulty service from consuming the entire lab
  host, with relatively more capacity assigned to PostgreSQL and the application tier.
- **Alternative considered:** `restart: always` would also restart after an intentional
  stop or daemon restart. No limits would reduce configuration but allow runaway memory,
  CPU, or process creation to affect every service.
- **Trade-off and limit:** These values are reasoned lab ceilings, not measurements from a
  load test. Tight memory limits can cause abrupt OOM termination, and restart loops can
  hide a persistent fault. Compose limits on a single machine do not provide horizontal
  capacity or host-level redundancy.
- **Evidence / commits:** `b6b59c7` (`reliability: gate startup on service health`) and
  `8f41bc4` (`reliability: set container resource limits`).
- **Production improvement:** Establish requests and limits from load tests and runtime
  metrics, alert on throttling/OOM/restart counts, add restart backoff, and autoscale
  replicas from service-level indicators.

## 6. Persist both data stores and test PostgreSQL recovery with real data

- **Choice:** Store PostgreSQL and Redis data in named volumes. Redis enables append-only
  persistence with `appendfsync everysec`. PostgreSQL backup uses a validated custom-format
  dump, a SHA-256 checksum, restrictive file permissions, and atomic rename; restore
  validates the dump and restores in a single transaction.
- **Why:** Recreating containers must not erase records or counters. A real backup/restore
  exercise proves recoverability more strongly than confirming that a dump command exits
  successfully.
- **Alternative considered:** Ephemeral container filesystems are simpler but lose state
  on recreation. Redis RDB snapshots write less often, while `appendfsync always` reduces
  the loss window further at a higher write cost.
- **Trade-off and limit:** `everysec` can lose about one second of Redis writes during a
  sudden failure. Named volumes remain on the same host and are not backups. The local
  PostgreSQL restore is destructive to the target database and requires an explicit dump,
  but it is not a point-in-time recovery system.
- **Evidence / commits:** `b9c817d` (`fix: persist PostgreSQL and Redis data`) and
  `4efcb56` (`feat: add PostgreSQL backup and restore tooling`).
- **Production improvement:** Use encrypted off-host backups, retention and access
  controls, continuous WAL archiving for point-in-time recovery, scheduled restore drills,
  and a documented recovery-time and recovery-point objective.

## 7. Inject credentials at runtime and keep secret files outside version control

- **Choice:** Compose requires `POSTGRES_PASSWORD` at interpolation time and constructs the
  application database URL from runtime environment values. `.env` and generated backup
  files are ignored; `.env.example` contains only a safe placeholder.
- **Why:** A missing credential should stop configuration immediately instead of starting
  with a known default. Runtime injection keeps the live value out of the Docker image,
  committed Compose file, and application source.
- **Alternative considered:** A default password makes setup easier but is likely to reach
  shared environments unchanged. Docker Compose secrets would improve file-based delivery,
  though local Compose still needs an external process to provision the secret.
- **Trade-off and limit:** Environment variables can be visible through container
  inspection to users with Docker access, and the earlier starter credential remains in
  Git history even though it was synthetic and rotated. Local `.env` storage has no
  rotation, audit, or access-control service.
- **Evidence / commit:** `0692d57` (`security: keep runtime credentials out of source and
  logs`).
- **Production improvement:** Retrieve short-lived credentials from a secret manager,
  scope database privileges, automate rotation, audit access, and prevent secret values
  from reaching logs or CI output.

## 8. Make validation broad, bounded, and scoped to one Compose project

- **Choice:** `validate.py` discovers services through exact Compose labels and checks
  health, network membership, port isolation, public endpoints, both application
  identities, PostgreSQL-backed record creation, and the Redis counter. Destructive
  failure and recovery testing is separate and restores the selected replica in a
  `finally` path. CI builds the same images, runs contract tests, starts the full stack,
  and executes end-to-end validation with time limits and cleanup.
- **Why:** Labels prevent scripts from acting on unrelated containers with similar names.
  Bounded waits and non-zero exits make failures useful to a person and to CI. Exercising
  the public path plus real dependencies catches errors that unit tests cannot.
- **Alternative considered:** Checking only container state or calling the app directly is
  faster but would miss proxy, network, identity, persistence, and dependency mistakes.
  Hard-coded container names would be brittle under project overrides and unsafe on a
  shared Docker host.
- **Trade-off and limit:** The end-to-end checks mutate synthetic application data. Green
  CI proves that one clean Ubuntu runner can build and pass the checked contracts at that
  commit; it does not prove capacity, long-running stability, security, backup durability,
  or behavior on every host platform.
- **Evidence / commits:** `50578d8` (`feat: add end-to-end environment validation`),
  `3b85907` (`test: automate backend failure and recovery`), and `91c7d44` / `c517ca0`
  (CI implementation and action pinning).
- **Production improvement:** Add load and soak tests, vulnerability and policy checks,
  multi-platform builds where required, external synthetic monitoring, and controlled
  deployment promotion with rollback evidence.

## Assumptions that bound these decisions

- Docker Engine and the Compose plugin are available, and the operator has trusted access
  to the local Docker daemon.
- The public endpoint is used from the same host; remote clients require a deliberate
  ingress and TLS design.
- Assessment records and credentials are synthetic. The backup directory is local evidence,
  not approved production backup storage.
- Application requests are modest and mainly I/O-bound. No performance target is claimed
  without load-test evidence.
- PostgreSQL, Redis, NGINX, and both application replicas share one host. Their container
  redundancy does not survive loss of that host.
