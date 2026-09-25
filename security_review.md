# Security and production-readiness review

This review assesses the repository as a local, synthetic-data lab. **Implemented control**
describes what the current commit actually provides. **Production follow-up** is planned
work and is not presented as complete.

## 1. Runtime secrets are excluded from source, but environment delivery is limited

- **Risk and evidence:** The starter configuration embedded a database credential. The
  current Compose file requires `POSTGRES_PASSWORD`, builds `DATABASE_URL` at runtime, and
  `.gitignore` excludes `.env` and `.env.*` while allowing only `.env.example`. The example
  value is an explicit placeholder. A synthetic starter credential remains in earlier Git
  history even though it was rotated locally.
- **Impact:** A committed or reused password can be copied from an image, repository, log,
  or CI output and used to read or alter data. Environment values are also visible to a
  user who already has Docker inspection access.
- **Implemented control / commit:** `0692d57` removes the credential from code and Compose,
  requires runtime injection, ignores secret files, and keeps a safe setup template.
- **Production follow-up:** Use a secret manager to issue short-lived credentials, mount or
  inject them only into the workloads that need them, restrict database privileges,
  automate rotation, and audit secret access. Scan Git history and revoke any real value
  immediately if one is ever committed.
- **How to verify:** Run `git grep` for the active value, confirm `.env` is ignored with
  `git check-ignore .env`, and confirm `docker compose config` fails when
  `POSTGRES_PASSWORD` is absent. Inspect the built image and application logs to verify the
  value is not stored or printed.

## 2. Host port exposure and east-west access are restricted, but transport is plaintext

- **Risk and evidence:** Publishing application, PostgreSQL, or Redis ports would bypass
  the proxy and expose internal protocols. The final Compose topology publishes only
  NGINX, binds it to `127.0.0.1`, gives NGINX only the `frontend` network, and places the
  data services only on the `internal: true` `backend` network. Traffic inside both Docker
  networks uses plaintext HTTP or native database/cache protocols.
- **Impact:** Reduced port exposure limits accidental access from the LAN and prevents the
  proxy from directly reaching data services. A process that compromises an application
  can still access both dependencies, and a sufficiently privileged host user can inspect
  local traffic.
- **Implemented control / commits:** `6367153`, `96943d8`, and `b243d59` establish one
  loopback entry point and separate frontend and backend traffic. `validate.py` checks the
  exact memberships, internal flag, and published-port boundary.
- **Production follow-up:** Terminate TLS at a managed ingress, use service-to-service TLS
  where the threat model requires it, enforce workload network policies and host firewall
  rules, and authenticate Redis with a scoped ACL rather than relying only on network
  reachability.
- **How to verify:** Run `./validate.py`; inspect `docker compose ps` to confirm that only
  NGINX has a published address; inspect each container's networks; and test that database
  and Redis ports are unreachable from the host and from the NGINX container.

## 3. The application is non-root, while infrastructure images need further hardening

- **Risk and evidence:** Running a compromised application as root increases the possible
  effect inside its container. The application image declares `USER app` with UID/GID
  10001 and copies application files with that ownership. Runtime inspection confirms the
  Gunicorn process uses UID 10001. The official PostgreSQL and Redis entrypoints start with
  the image default user and drop their server processes to `postgres` and `redis`;
  NGINX keeps a root master process so it can bind port 80 while workers run as `nginx`.
- **Impact:** The primary application attack surface has reduced privileges, but container
  isolation is not a complete security boundary. A root master process, default Linux
  capabilities, and a writable root filesystem increase the effect of an image or daemon
  vulnerability.
- **Implemented control / commit:** `e11fe0d` creates the dedicated application identity,
  runs Gunicorn as that identity, and avoids privileged mode. Read-only bind mounts protect
  the database initialization and NGINX configuration files.
- **Production follow-up:** Run NGINX rootless on an unprivileged internal port, set an
  explicit service user where supported, drop all unneeded capabilities, enable
  `no-new-privileges`, use read-only root filesystems with explicit writable mounts, and
  apply the platform's seccomp/AppArmor/SELinux controls.
- **How to verify:** Inspect image `Config.User`, run `id` and inspect PID 1 inside each
  container, confirm no service is privileged, and inspect effective capabilities and
  writable mounts. The application should report UID/GID 10001.

## 4. Image and dependency versions are pinned, but patching and provenance are manual

- **Risk and evidence:** Mutable tags can change between builds, while stale pinned images
  retain known vulnerabilities. Python, PostgreSQL, Redis, and NGINX base images are
  pinned by digest; Python packages are pinned to exact versions in `requirements.txt`.
  The repository has no vulnerability scan, SBOM, signature verification, or automated
  update policy.
- **Impact:** Builds are repeatable, but a newly disclosed operating-system or package
  vulnerability will remain until the digest or dependency version is deliberately
  updated and retested.
- **Implemented control / commits:** `e11fe0d` uses the slim Python base, and the current
  Compose file pins all third-party service images. `c517ca0` also pins the CI checkout
  action to an exact commit.
- **Production follow-up:** Generate and retain an SBOM, scan source and built images,
  verify signatures or attestations, run scheduled dependency updates, define remediation
  deadlines by severity, and rebuild even when application code does not change.
- **How to verify:** Resolve every `FROM`, Compose `image`, and GitHub Action reference;
  confirm container images use `@sha256` and dependencies use exact versions. Run an image
  and dependency scanner and fail the release policy on unaccepted findings.

## 5. Data survives recreation and PostgreSQL restore is proven, but backups are local

- **Risk and evidence:** Container filesystems are ephemeral. PostgreSQL and Redis now use
  named volumes, and Redis uses AOF with `appendfsync everysec`. `backup.sh` writes a
  validated PostgreSQL custom-format dump through a temporary file, applies mode 0600,
  performs an atomic rename, and prints a SHA-256 checksum. `restore.sh` validates its
  input and restores with `--exit-on-error --single-transaction`. A completed drill proved
  that pre-backup data returned and post-backup data disappeared after restore.
- **Impact:** Routine container replacement no longer erases state, and the restore test
  catches unusable dumps. The volumes and dump still share the same workstation failure
  domain. Redis can lose roughly one second of acknowledged changes, and PostgreSQL has no
  point-in-time recovery.
- **Implemented control / commits:** `b9c817d` adds persistent volumes; `4efcb56` adds the
  scoped backup and restore tooling and records a real recovery test.
- **Production follow-up:** Encrypt backups, copy them to access-controlled off-host
  storage, define retention, enable WAL archiving and point-in-time recovery, monitor job
  results, and schedule isolated restore drills against documented RPO and RTO targets.
- **How to verify:** Create a uniquely marked record, back up, create a second marker,
  restore, and prove only the first marker remains. Verify the checksum and file mode, then
  test recovery from the off-host copy on a separate database.

## 6. Logs support correlation without exposing exception text, but monitoring is absent

- **Risk and evidence:** Unstructured or secret-bearing logs slow incident response and can
  disclose credentials. NGINX and the application emit JSON with timestamps, request IDs,
  status, latency, instance identity, and dependency name. Application dependency failures
  record only the exception type, not the connection string or exception message. NGINX
  records `$uri`, which excludes query arguments. Logs currently remain in Docker's local
  logging path; there are no metrics, traces, alerts, retention controls, or centralized
  access policy.
- **Impact:** The supplied incident logs can be correlated across layers, but a host loss or
  log rotation can remove evidence. Operators will not be notified automatically about
  elevated 5xx rates, slow requests, unhealthy services, restarts, or storage pressure.
- **Implemented control / commit:** The application and NGINX logging are part of the
  repaired environment, and `2cbe8c6` demonstrates request-ID correlation and exact-line
  deduplication across the supplied logs.
- **Production follow-up:** Forward structured logs to centralized protected storage, add
  RED/USE metrics and distributed traces, define retention and redaction rules, synchronize
  clocks, and alert on service-level indicators such as error rate, p95 latency, dependency
  failures, restarts, and backup age.
- **How to verify:** Send a request with a traceable ID, locate matching NGINX and
  application events, and confirm secrets and request bodies are absent. Trigger a safe
  dependency failure in staging and verify the dashboard, alert, and runbook link.

## 7. Health checks and two replicas improve recovery, but major single points remain

- **Risk and evidence:** Both application replicas have health checks and NGINX waits for
  them at startup. Every service uses `restart: unless-stopped`. The automated failure test
  safely stops one labelled application container, measures the public result, restores
  the same container, and proves it serves again. With proxy retries intentionally disabled,
  the observed one-replica outage produced about 50% failed requests. NGINX, PostgreSQL,
  Redis, the Docker daemon, and the host each remain a single point of failure.
- **Impact:** Process crashes can recover automatically, but losing any singleton or the
  host can interrupt all requests. Keeping a stopped upstream in round-robin rotation
  causes avoidable client failures during the outage.
- **Implemented control / commits:** `b6b59c7` adds health-gated startup and restart policy;
  `3b85907` adds bounded failure/recovery measurement with guaranteed cleanup.
- **Production follow-up:** Distribute application replicas across failure domains, use a
  redundant managed load balancer, deploy PostgreSQL high availability with tested
  failover, choose an appropriate Redis HA design, and remove unhealthy endpoints through
  active readiness. Retry only safe idempotent operations within a bounded latency budget.
- **How to verify:** Run `./failure_test.py` in the lab and confirm recovery, then exercise
  node and dependency failover in staging while measuring availability, recovery time,
  data consistency, and client-visible errors.

## 8. Timeouts and resource limits bound failures, but values lack capacity evidence

- **Risk and evidence:** Unlimited work can exhaust the shared host or leave requests
  hanging. Application dependency connections and SQL statements are bounded at two
  seconds, NGINX uses two-second connect and three-second read timeouts, and Gunicorn uses
  a 30-second worker timeout. All containers have CPU, memory, and PID ceilings. These
  resource values were chosen for the lab rather than derived from load, soak, or failure
  testing.
- **Impact:** One faulty process is less able to consume the whole host, but low limits can
  cause throttling or OOM termination. Misaligned timeouts can cause NGINX to return 504
  while an application continues work; this exact pattern appears in the supplied logs.
- **Implemented control / commits:** `8f41bc4` defines resource ceilings, while `2cbe8c6`
  records the observed latency and timeout relationship.
- **Production follow-up:** Establish an end-to-end latency budget, load-test realistic
  traffic, align client/proxy/application/dependency timeouts, size requests and limits
  from measured percentiles, and alert on throttling, OOM kills, queueing, and restart
  loops.
- **How to verify:** Inspect the runtime CPU, memory, and PID settings; generate controlled
  load; compare client, proxy, application, and dependency timing; and verify overload
  fails predictably without destabilizing unrelated services.

## 9. Basic input and SQL handling are safe, but the API has no access control

- **Risk and evidence:** The application caps request bodies at 16 KiB, restricts record
  titles to 1-200 nonblank characters, validates instance IDs and request IDs, and passes
  titles to PostgreSQL as parameters. Error responses are generic. The API has no
  authentication, authorization, rate limiting, audit identity, CSRF model, or TLS because
  it is bound to the local assessment endpoint.
- **Impact:** Parameterized SQL and validation reduce injection and resource abuse, but any
  process able to reach the endpoint can list or create records and increment the counter.
  If the same service were exposed publicly, anonymous abuse and data access would be
  immediate risks.
- **Implemented control / commit:** Input validation and parameterized queries are present
  in `app/server.py`; `91c7d44` runs application contract tests and end-to-end checks in CI.
- **Production follow-up:** Define an identity and authorization model, require TLS, add
  per-identity rate limits and audit events, restrict allowed methods and content types,
  and set browser security headers appropriate to the actual client. Perform threat
  modelling before adding public ingress.
- **How to verify:** Run unit tests for malformed JSON, oversized bodies, invalid titles,
  and SQL metacharacters. In staging, verify anonymous and unauthorized requests are
  rejected, rate limits apply, TLS settings meet policy, and audit records identify the
  caller without logging credentials.

## 10. CI validates behavior with limited permissions, but it is not a release security gate

- **Risk and evidence:** CI uses read-only repository permissions, a pinned checkout action,
  a 15-minute job timeout, synthetic credentials, concurrency cancellation, and cleanup on
  every outcome. It compiles scripts, checks Compose and shell syntax, builds images, runs
  contract tests, starts the full environment, and runs end-to-end validation. It does not
  scan for leaked secrets or vulnerabilities, create provenance, test backup restore, run
  the failure test, or enforce repository branch protection.
- **Impact:** A green run proves the checked behavior on one clean Ubuntu runner at that
  commit. It does not prove that the artifact is vulnerability-free, production-ready,
  deployable on every platform, or protected from an unreviewed merge.
- **Implemented control / commits:** `91c7d44` creates the complete validation job and
  `c517ca0` pins its third-party action. The matching workflow run provides remote evidence
  for each pushed commit.
- **Production follow-up:** Add secret, dependency, image, IaC, and license scanning; create
  signed build provenance and SBOMs; protect the release branch with review and required
  checks; test recovery in an isolated job; and promote immutable artifacts instead of
  rebuilding them at deployment time.
- **How to verify:** Review effective workflow permissions and action references, inspect a
  clean successful run, confirm cleanup after a forced failure, and check repository rules
  require the expected reviews and security jobs before merge or release.

## Overall production-readiness limit

The repository demonstrates a secured and testable local Compose environment. It does not
claim production readiness because it lacks multi-host redundancy, managed secrets,
authenticated encrypted ingress, centralized observability, off-host recovery, supply-chain
policy, and measured capacity. Those gaps require platform design and operational evidence,
not documentation alone.
