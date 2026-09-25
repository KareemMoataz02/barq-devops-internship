# Troubleshooting journal

## 2026-09-24 16:16–16:17 UTC — reproduce the supplied baseline

### Scope and provenance

This guided investigation starts from supplied commit `8442da3` with the original
release history and `starter-v2.0.0` tag preserved. This is a new execution of the
starter, not a claim that no previous preparation exists. No runtime repair has been
applied in this entry. The video challenge has not been executed.

Other lab containers already occupy the names required by the final demonstration.
To keep their data untouched, this diagnostic run uses project `barq-guided` and a
local override that changes only container names. Service names, application settings,
ports, mounts, networks, and the supplied source files remain unchanged.

### Reproduce this diagnostic setup

From the starter directory:

```bash
mkdir -p evidence/local/guided-baseline
cat > evidence/local/guided-baseline/diagnostic.override.yml <<'YAML'
services:
  app-01:
    container_name: barq-guided-app-01
  app-02:
    container_name: barq-guided-app-02
  nginx:
    container_name: barq-guided-nginx
  postgres:
    container_name: barq-guided-postgres
  redis:
    container_name: barq-guided-redis
YAML

docker compose -p barq-guided -f docker-compose.yml \
  -f evidence/local/guided-baseline/diagnostic.override.yml config --quiet

docker compose -p barq-guided -f docker-compose.yml \
  -f evidence/local/guided-baseline/diagnostic.override.yml up --build -d

docker compose -p barq-guided -f docker-compose.yml \
  -f evidence/local/guided-baseline/diagnostic.override.yml ps -a
```

The final recorded setup must use the required container names. The temporary
names above are for the isolated diagnostic phase only. Generated local evidence is
ignored by Git; this journal records the relevant observations without credentials.

### Actual observations

Compose syntax validation returned exit 0. The build/start command also returned
exit 0. Inspection immediately afterward showed:

| Service | Runtime state | Evidence |
|---|---|---|
| app-01 | Running, unhealthy | Repeated `GET /healthz` returns 404 |
| app-02 | Running, unhealthy | Repeated `GET /healthz` returns 404 |
| nginx | Exited, code 1 | Opening `/etc/nginx/nginx.conf` fails with permission denied |
| postgres | Exited, code 1 | Reading `/docker-entrypoint-initdb.d/01-init.sql` fails with permission denied |
| redis | Running, healthy | Docker health status is healthy |

A bounded request to `http://127.0.0.1:8080/health` failed with connection refused.
A direct request inside app-01 to `/health` returned HTTP 200:

```bash
docker exec barq-guided-app-01 python -c \
  'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=2).status)'
```

### Issue 1 — incorrect app health endpoint

- Symptom: both application containers report unhealthy despite running processes.
- Hypothesis: the configured health probe does not match the application's routes.
- Commands: inspect the Compose healthcheck and `app/server.py` route declarations;
  compare logged `/healthz` responses with the direct `/health` request above.
- Result: Compose probes `/healthz`; the app implements `/health`; observed responses
  are 404 and 200 respectively.
- Confirmed cause: endpoint mismatch.
- Fix: not yet applied. Next step is a focused healthcheck correction.
- Retest required: both Docker app health states become healthy after recreation.
  This alone will not prove public access or database readiness.

### Issue 2 — bind-mounted files are not readable inside services

- Symptom: NGINX and PostgreSQL exit while reading their configuration/init files.
- Hypothesis: SELinux labels deny container access to host bind mounts.
- Evidence: SELinux enforcement is `1`; `ls -lZ nginx/nginx.conf database/init.sql`
  shows mode `0644` and label `unconfined_u:object_r:user_home_t:s0` for both files.
  The supplied Compose mounts have `:ro` without a container relabel option.
- Status: likely cause, not yet proven by a repair. Ordinary file readability does
  not rule out SELinux restrictions.
- Fix: not yet applied. Test container-compatible labels and inspect service recovery.
- Retest required: both services can read those files. Other independent faults may
  still prevent the full environment from working.

### Failed expectations and limits

- The successful syntax/start commands did not imply working services. Actual state,
  logs, and HTTP requests contradicted that assumption.
- No failed repair is claimed: no repair has been attempted in this stage.
- Further configuration mismatches remain to be investigated separately.
- There is no CI workflow in the supplied starter; adding one is a later task.
- Local command output is in `evidence/local/guided-baseline/`.
- Related commit: `docs: record baseline startup and health-check failures`.

## 2026-09-24T16:55:54.774627+00:00 — correct the application health probe

- Symptom before the change: both diagnostic app containers were running but
  unhealthy; the configured `/healthz` endpoint returned 404.
- Change: replace `/healthz` with the implemented `/health` endpoint in the shared
  Compose app healthcheck. The anchor applies this one-line fix to both app services.
- Validation: Compose syntax passed. Recreate only the two app containers using
  the same diagnostic override; use `--no-deps` to leave other services untouched.

```bash
docker compose -p barq-guided -f docker-compose.yml \
  -f evidence/local/guided-baseline/diagnostic.override.yml config --quiet

docker compose -p barq-guided -f docker-compose.yml \
  -f evidence/local/guided-baseline/diagnostic.override.yml up -d --no-deps app-01 app-02

docker inspect barq-guided-app-01 barq-guided-app-02 \
  --format '{{.Name}} {{.State.Status}} {{.State.Health.Status}}'
```

- Actual result: both containers changed from unhealthy to healthy. Their latest
  health probes returned exit 0. A bounded health-state check used a 45-second limit.
- Confirmed cause and fix: the healthcheck path was incorrect; correcting only that
  path restored both app health states.
- Failed repair attempts: none in this step.
- Evidence: `evidence/local/guided-baseline/healthcheck-retest.json` contains the
  inspection timestamp, actual probe commands, states, and exit codes.
- Scope of proof: the application processes respond to local liveness probes.
  This does not prove NGINX connectivity, dependency readiness, or persistence.
- Remaining issues: NGINX/PostgreSQL mounted-file access and other starter
  configuration defects have not been repaired.
- Related commit: `fix: use the implemented application health endpoint`.

## 2026-09-24 16:58 UTC — allow containers to read bind-mounted files

- Symptom before the change: NGINX exited because it could not open
  `/etc/nginx/nginx.conf`; PostgreSQL exited because it could not read
  `/docker-entrypoint-initdb.d/01-init.sql`.
- Hypothesis: SELinux enforcement blocked both bind mounts because the host files
  had `user_home_t` labels and the Compose mounts requested read-only access without
  container relabeling.
- Focused change: add `Z` to the two read-only bind-mount modes (`ro,Z`). `Z` gives
  each bind mount a private container SELinux label while preserving read-only access.
- Validation commands:

```bash
docker compose -p barq-guided -f docker-compose.yml \
  -f evidence/local/guided-baseline/diagnostic.override.yml config --quiet

docker compose -p barq-guided -f docker-compose.yml \
  -f evidence/local/guided-baseline/diagnostic.override.yml \
  up -d --force-recreate postgres nginx

docker inspect barq-guided-nginx barq-guided-postgres
docker exec barq-guided-nginx nginx -t
ls -lZ nginx/nginx.conf database/init.sql
```

- Actual result: NGINX remained running with exit code 0 and `nginx -t` passed.
  PostgreSQL remained running, became healthy, executed `01-init.sql`, created the
  records table, inserted two starter rows, and accepted connections. Both host
  files changed to `container_file_t` labels with private MCS categories.
- Confirmed root cause: missing container-compatible SELinux labels caused both
  permission failures. The focused relabeling removed those failures.
- Failed repair attempts: none in this step.
- Negative retest: public `/` and `/health` still reset the connection. Docker maps
  host port 8080 to container port 81, while NGINX configuration listens on port 80.
  Therefore this commit does not claim to restore public access.
- Persistence limitation observed: PostgreSQL still stores its active data directory
  on tmpfs while the named volume targets `/var/lib/postgresql/backup`. Persistence
  remains unproven and is not fixed here.
- Related commit: `fix: label bind mounts for SELinux containers`.

## 2026-09-24 — align the published port with the NGINX listener

- Symptom before the change: the host connection reached Docker port 8080 but reset;
  inspection showed host 8080 forwarded to container port 81, while the supplied
  NGINX configuration listens on container port 80.
- Hypothesis: the published container port does not have a listening process.
- Focused change: map `127.0.0.1:${PUBLIC_PORT:-8080}` to NGINX container port 80.
  Keep the host binding on loopback and retain the required preparation port 8080.
- Validation: Compose syntax passed; only NGINX was force-recreated. `docker port`
  then reported `80/tcp -> 127.0.0.1:8080`, and NGINX remained running with exit 0.
- Actual HTTP result: six bounded requests to the public `/health` URL all reached
  NGINX and returned HTTP 502. Before this change the same URL reset the connection.
- Confirmed cause and fix: the incorrect published target port prevented the host
  from reaching NGINX; mapping to its real listener restored the public edge path.
- New evidence from the next hop: connection probes from NGINX to `app-01:8080`,
  `app-01:8081`, and `app-02:8080` all failed. Both app environments currently set
  `APP_HOST=127.0.0.1`, so their processes accept only same-container connections.
  NGINX also configures app-01 on port 8081 while the app uses port 8080.
- Failed repair attempts: none in this step. The 502 responses are a separate upstream
  defect revealed after the edge port began working, not failure of the port fix.
- Scope of proof: host-to-NGINX connectivity is restored. No successful response has
  yet passed from NGINX to an app.
- Related commit: `fix: publish the active NGINX listener`.

## 2026-09-24 — expose application listeners to NGINX

- Symptom before the change: public requests reached NGINX but returned HTTP 502.
  Connection probes from the NGINX container to both application services failed.
- Confirmed causes: the shared application configuration bound Flask to
  `127.0.0.1`, which accepts traffic only from inside its own container. NGINX also
  targeted app-01 on port 8081 even though both applications use port 8080.
- Focused change: bind the applications to `0.0.0.0` and target app-01 on port 8080.
- Validation: Compose syntax passed and app-01, app-02, and NGINX were recreated.
  Both application containers became healthy within the 45-second bounded check.
  TCP probes from NGINX reached `app-01:8080` and `app-02:8080` successfully.
- Actual HTTP result: six public `/health` requests returned HTTP 200. Four public
  `/instance` requests also returned HTTP 200, and the NGINX access log showed that
  requests reached both application container IP addresses.
- Confirmed result: the public request path now works from host port 8080 through
  NGINX to both application containers.
- Newly isolated issue: every `/instance` response reports `app-01`, including the
  response served by app-02's container IP. The app-02 service has a duplicate
  `INSTANCE_ID`; that identity defect remains for a separate focused repair.
- Failed repair attempts: none in this step.
- Related commit: `fix: expose app listeners to the frontend network`.

## 2026-09-24 — give app-02 a distinct instance identity

- Symptom before the change: NGINX logs showed requests reaching both application
  container IP addresses, but every `/instance` response reported `app-01`.
- Confirmed cause: the Compose service definitions assigned `INSTANCE_ID=app-01`
  to both app-01 and app-02.
- Focused change: set app-02's `INSTANCE_ID` to `app-02` and recreate only that
  application container.
- Validation: Compose syntax passed, app-02 became healthy within the 45-second
  bounded check, and twelve public `/instance` requests succeeded through NGINX.
- Actual result: the responses alternated evenly between `app-01` and `app-02`,
  with six responses from each identity.
- Confirmed result: the public endpoint now demonstrates two distinct application
  instances and NGINX round-robin load balancing.
- Failed repair attempts: none in this step.
- Related commit: `fix: give app-02 a distinct instance identity`.

## 2026-09-24 — restore PostgreSQL and Redis readiness

- Symptom before the change: `/ready` returned HTTP 503 and reported both PostgreSQL
  and Redis unavailable.
- Initial evidence: the app connection URLs used PostgreSQL port 5433 and Redis port
  6380. Direct probes from app-01 proved the services were reachable on their actual
  internal ports, PostgreSQL 5432 and Redis 6379.
- First focused change: correct both internal ports in `config/app.env` and recreate
  the two application containers.
- Intermediate result: Redis became ready and `/counter` returned HTTP 200, but
  PostgreSQL remained unavailable and `/records` still returned HTTP 503.
- Follow-up evidence: a redacted comparison of the running environments showed that
  the database name and username matched, while the app and PostgreSQL passwords did
  not. No credential value was printed during that comparison.
- Second focused change: align the app's database URL with PostgreSQL's configured
  credential and recreate the two application containers.
- Final validation: both apps became healthy within the bounded wait; `/ready`
  returned HTTP 200 with both dependencies ready; `/records` returned the two seeded
  rows; and two `/counter` requests returned HTTP 200 and advanced the shared count
  from 3 to 4 across app-01 and app-02.
- Failed validation attempt: the first endpoint loop used zsh's reserved `path`
  variable, which temporarily hid executable lookup and exited 127 before making the
  requests. Renaming the loop variable to `endpoint` fixed the test command; no
  application change was made in response to that shell error.
- Remaining security issue: a credential is still stored in a tracked environment
  file, and application startup logging currently emits complete connection URLs.
  Those risks remain for a separate security-focused change.
- Related commit: `fix: correct dependency connection settings`.

## 2026-09-24 — remove credentials from tracked files and logs

- Security findings: the database credential appeared in `docker-compose.yml` and
  `config/app.env`; the Dockerfile copied that environment file into the image; and
  application startup logs emitted complete PostgreSQL and Redis URLs.
- Focused change: use Compose interpolation from an ignored root `.env`, add safe
  variable names and placeholder values to `.env.example`, remove `config/app.env`,
  stop copying it into the image, and log only boolean configured states.
- Credential response: generate a new local database password, update the ignored
  `.env`, alter the PostgreSQL role to use it, and recreate both app containers. The
  replacement credential was not printed or added to Git.
- Static validation: Compose rendered successfully, `.env` was confirmed ignored,
  the focused diff passed whitespace checks, and a current-tree scan found zero
  matches for the removed lab credential or full-URL startup log statements.
- Image validation: both app images rebuilt successfully, and inspection of `/srv`
  in the rebuilt image found no environment file.
- Application validation: all eight contract tests passed inside the application
  image. Both recreated apps became healthy and public `/ready` returned HTTP 200
  with PostgreSQL and Redis ready after credential rotation. Startup logs contain
  only `database_configured=true` and `redis_configured=true`.
- Failed validation attempt: running the unit suite with the host Python failed at
  import time because the host lacked the declared `psycopg` package. Running the
  same suite inside the project image supplied the declared dependencies and passed.
- Failed edit attempt: the first `apply_patch` request used content lines with the
  delete-file directive, which that patch format rejects. It made no filesystem
  change; the corrected delete-file directive then removed `config/app.env`.
- Historical limitation: the former lab credential remains visible in earlier Git
  commits, but rotating it invalidated that value. Rewriting the supplied progressive
  history would conflict with the assessment's requirement to preserve that history.
- Related commit: `security: keep runtime credentials out of source and logs`.

## 2026-09-24 — enforce frontend and backend network isolation

- Security findings: the submitted Compose file published PostgreSQL on host port
  15432 and Redis on host port 16379. NGINX also joined the backend network, giving
  the public edge container unnecessary access to both data services.
- Focused change: remove the PostgreSQL and Redis host port mappings and attach
  NGINX only to the frontend network. Keep both apps on frontend and backend, and
  keep PostgreSQL and Redis only on the internal backend network.
- Static validation: the rendered base Compose model showed only NGINX publishing a
  port (`127.0.0.1:8080`), NGINX on frontend, both apps on frontend and backend, and
  PostgreSQL and Redis on backend. Compose syntax and whitespace checks passed.
- Runtime isolation proof: container inspection showed no published ports for either
  app or data service. NGINX had only the frontend network and could not resolve the
  `postgres` service name, while app-01 resolved both `postgres` and `redis` through
  the backend network.
- Functional validation: public `/ready` returned HTTP 200 with both dependencies
  ready. After the fresh NGINX start, the first four `/instance` requests selected
  app-01; a 100-request sample then returned 51 app-01 and 49 app-02 responses,
  confirming that both frontend paths remained available and balanced.
- Failed repair attempts: none in this step.
- Related commit: `security: isolate data services on the backend network`.

## 2026-09-24 — persist PostgreSQL and Redis data

- Persistence findings: PostgreSQL reported `/var/lib/postgresql/data` as its active
  data directory, but Compose placed that directory on tmpfs and mounted the named
  volume at the unused `/var/lib/postgresql/backup` path. Redis explicitly disabled
  snapshots and AOF and used only an anonymous image-created `/data` volume.
- Focused change: mount `postgres-data` at `/var/lib/postgresql/data` and remove the
  tmpfs. Enable Redis AOF with `appendfsync everysec`, mount a new named `redis-data`
  volume at `/data`, and declare that volume in Compose.
- Initial validation: Compose rendered both named volumes at their active data paths.
  PostgreSQL and Redis were recreated, became healthy, public `/ready` returned HTTP
  200, and Redis reported `appendonly=yes`.
- Persistence test data: create PostgreSQL record ID 3 with title
  `persistence-proof-20260924`, advance the Redis counter to 1, and use `WAITAOF` to
  confirm one local AOF write before replacement.
- Replacement proof: force-recreate both PostgreSQL and Redis, then wait for both
  health checks. `/records` still returned record ID 3, `/counter` continued from 1
  to 2, and `/ready` returned HTTP 200 with both dependencies ready.
- Mount proof: runtime inspection showed `barq-guided_postgres-data` mounted at
  `/var/lib/postgresql/data` and `barq-guided_redis-data` mounted at `/data`.
- Failed repair attempts: none in this step.
- Related commit: `fix: persist PostgreSQL and Redis data`.

## 2026-09-24 — run application containers as non-root with Gunicorn

- Runtime findings: the image created user `app` with UID/GID 10001 but switched
  back to root. Both live containers ran Flask's built-in development server as UID
  0. Gunicorn was already pinned in `requirements.txt` but unused.
- Focused change: keep `USER app` as the final image user and replace the Flask
  development command with Gunicorn bound to port 8080, using two workers, two
  threads per worker, a 30-second timeout, and stdout/stderr logs.
- Static and build validation: Compose syntax and whitespace checks passed,
  `docker build --check` reported no warnings, and both app images rebuilt.
- Test validation: all eight contract tests passed inside the rebuilt image while
  running as UID 10001.
- Runtime proof: both recreated containers became healthy. `id` reported UID/GID
  10001, and process inspection showed docker-init, one Gunicorn master, and two
  Gunicorn workers all running as UID 10001 in each container.
- Functional validation: public `/ready` returned HTTP 200 with both dependencies
  ready; twenty `/instance` requests split evenly, 10 per app; and `/records` still
  contained the PostgreSQL persistence marker from the preceding container cycle.
- Failed validation attempt: the first non-root test run bind-mounted the repository,
  whose root directory is mode 0700 and owned by the host user. UID 10001 therefore
  could not traverse the mount. A readable temporary copy isolated the test inputs
  and the suite passed without changing repository permissions.
- Blocked command attempt: the command runner rejected a shell cleanup using
  `rm -rf` before execution. Python's temporary-directory lifecycle provided bounded
  cleanup instead; no repository or test change resulted from the rejection.
- Related commit: `security: run apps as non-root with Gunicorn`.

## 2026-09-24 — add health-gated startup and automatic recovery

- Lifecycle findings: the apps used `restart: no`, the other services had no restart
  policy, apps had no dependency gates, NGINX waited only for containers to start,
  and NGINX had no health check. PostgreSQL's probe also hardcoded the default user
  and database even though both values are configurable.
- Focused change: apply `restart: unless-stopped` to all five services; wait for
  healthy PostgreSQL and Redis before starting the apps; wait for both healthy apps
  before starting NGINX; add an NGINX `/health` probe; and read PostgreSQL probe
  values from its runtime environment.
- Static validation: Compose syntax and whitespace checks passed. The rendered model
  showed the two service-health dependency levels, a health check for every service,
  and `unless-stopped` for all five services.
- Cold-start proof: bring down all guided-project containers without deleting named
  volumes, then start with Compose's 60-second health wait. PostgreSQL and Redis
  became healthy first, both apps started and became healthy next, NGINX started
  last, and all services reached healthy state in about 19 seconds.
- Recovery proof: send SIGTERM to app-01 PID 1 from inside the container. Docker
  increased its restart count from 0 to 1 and returned the service to healthy within
  the bounded 45-second check.
- Functional validation: all five services reported running and healthy with the
  expected restart policy, public `/ready` returned HTTP 200 with both dependencies
  ready, and the PostgreSQL persistence marker remained present after the cold start.
- Failed repair attempts: none in this step.
- Related commit: `reliability: gate startup on service health`.

## 2026-09-24 — bound container resource consumption

- Resource finding: runtime inspection reported zero CPU and memory limits and no PID
  limit for every service, allowing a single faulty container to consume the host.
- Focused change: limit each app to 0.50 CPU, 256 MiB, and 128 PIDs; PostgreSQL to
  0.75 CPU, 512 MiB, and 256 PIDs; and Redis and NGINX each to 0.25 CPU, 128 MiB,
  and 128 PIDs.
- Static validation: Compose syntax and whitespace checks passed. The rendered model
  converted the requested limits to the expected CPU fractions, byte counts, and PID
  counts for all five services.
- Runtime validation: force-recreate the complete stack with the 60-second health
  wait. All five services became healthy. Docker inspection reported the exact CPU,
  memory, and PID limits requested for each container.
- Observed headroom: the no-load snapshot showed PostgreSQL using about 19 MiB,
  Redis 4 MiB, app-01 97 MiB, app-02 90 MiB, and NGINX 8 MiB, all below their
  configured memory ceilings. Process counts ranged from 6 to 9, also below limits.
- Functional validation: public `/ready` returned HTTP 200 with both dependencies
  ready, and the PostgreSQL persistence marker remained present after recreation.
- Failed repair attempts: none in this step.
- Related commit: `reliability: set container resource limits`.

## 2026-09-25 — add end-to-end environment validation

- Deliverable: replace the `validate.py` placeholder with a bounded Python preflight
  that uses only the standard library and the Docker CLI. It accepts an explicit
  Compose project and loopback URL so the guided environment can be tested without
  selecting unrelated containers by name.
- Runtime checks: discover services using Compose labels; require all containers to
  be running and healthy; verify NGINX, application, PostgreSQL, and Redis network
  membership; require the backend network to be internal; and prove that only NGINX
  publishes the expected loopback port.
- Application checks: call `/`, `/health`, `/ready`, `/instance`, `/records`, and
  `/counter`; create and list a uniquely named PostgreSQL record; verify the Redis
  counter advances by one; validate response correlation and instance headers; and
  sample the load balancer until every discovered application replica responds.
- The record creation and two counter requests are intentional test data mutations.
  The script never stops, recreates, or removes a container, network, or volume.
- Validation command:

```bash
./validate.py --project barq-guided --url http://127.0.0.1:8080
```

- Actual result: exit 0. Compose syntax passed; all five containers were healthy;
  the frontend/internal-backend topology and port isolation passed; every public
  endpoint and both dependencies worked; and traffic reached app-01 and app-02.
- Negative-path proof: an HTTPS non-loopback URL was rejected immediately with exit
  1 before Docker or the endpoint checks ran.
- Failed validation attempts: the first live run compared HTTP header names with
  case-sensitive spelling, then revealed that NGINX generates the public request ID
  instead of preserving a caller-supplied value. The script now applies HTTP's
  case-insensitive header rules and validates the returned correlation ID and matching
  instance identity. No service configuration was changed for this script defect.
- Related commit: `feat: add end-to-end environment validation`.

## 2026-09-25 — measure one-backend failure and recovery

- Deliverable: replace the `failure_test.py` placeholder with a bounded test that
  selects one application container by exact Compose project and service labels.
  The default target is app-01, and only an `app-NN` service on an HTTP loopback URL
  is accepted.
- Safety behavior: require a healthy target and healthy public endpoint before the
  fault; mark restoration as required before stopping the container; and use a
  `finally` block to start it and wait for Docker health even when measurement fails
  or the test is interrupted. No network, volume, or unrelated container is changed.
- Failure behavior: stop app-01 and send 60 concurrent `/instance` requests through
  NGINX. Require both successful requests and proxy errors, and reject any response
  claiming to come from the stopped replica. NGINX intentionally has upstream retry
  disabled, so the errors expose the current availability limitation.
- Recovery behavior: start the same container ID, wait up to 45 seconds for healthy
  state, and sample public traffic until app-01 itself responds.
- Validation command:

```bash
./failure_test.py --project barq-guided --service app-01 \
  --url http://127.0.0.1:8080 --requests 60
```

- Actual retest: exit 0. During the 8.01-second fault sample, 29 requests succeeded
  through app-02 and 31 returned HTTP 504, for 48.3% measured availability. App-01
  restarted, became healthy, and then served a public request.
- Post-test proof: the complete `validate.py` check passed immediately afterward;
  all five containers were healthy and both app identities served traffic.
- Adjustment after the first successful run: sequential requests took about one
  minute because each failed selection waited for the upstream timeout. Running ten
  bounded requests concurrently preserves the same observable fault while reducing
  the demonstration to eight seconds and reporting duration and availability.
- Negative-path proof: a non-loopback HTTPS URL exits 1 before container selection.
- Failed repair attempts: none. The observed 502/504 responses are the measured
  behavior of the configured no-retry proxy, not a test failure.
- Related commit: `test: automate backend failure and recovery`.

## 2026-09-25 — create and prove a real PostgreSQL backup restore

- Deliverables: replace `backup.sh` and `restore.sh` placeholders with scripts that
  locate PostgreSQL by exact Compose project/service labels, require a running healthy
  container, use bounded Docker operations, and never place database credentials in
  the host command line.
- Backup behavior: run `pg_dump` in custom format inside the container, omit ownership
  and privilege metadata, validate the archive with `pg_restore --list`, copy through
  temporary paths, set host permissions to `0600`, and atomically move the completed
  archive to its requested path. Backups remain ignored by Git.
- Restore behavior: require an explicit readable non-empty file, validate it before
  changing the database, then use `pg_restore --clean --if-exists --exit-on-error`
  in one transaction. Verify the restored `records` table with a real SQL count.
- Proof sequence and commands:

```bash
# POST /records with title backup-restore-proof-20260925-a91f
./backup.sh --project barq-guided \
  --output backups/restore-proof-20260925-a91f.dump
# POST /records with title post-backup-only-20260925-a91f
./restore.sh --project barq-guided \
  --input backups/restore-proof-20260925-a91f.dump
```

- Before the dump, the API created backup marker ID 6. After the dump, it created
  post-backup marker ID 7. The custom archive was 2,361 bytes with SHA-256
  `ce1a7653650d0d91a5afa1861a118748d9d6a982247573490b627fed134d56eb`.
- Actual restore result: exit 0 and six rows restored. The API then returned the
  backup marker, did not return the post-backup marker, and reported both dependencies
  ready. This proves the records came from the archive rather than the current volume.
- Post-restore proof: the complete validation script passed; all five containers were
  healthy and both application replicas served public traffic.
- Negative-path proof: running restore without `--input` exited 1 before container
  selection or database changes.
- Failed validation attempt: the first ShellCheck run returned SC2016 because it
  cannot infer that three single-quoted variable references must expand inside the
  PostgreSQL container. Inline suppressions now document that trust boundary; Bash
  syntax and ShellCheck both pass.
- Limitation: the lab restore runs against the live database and can briefly interrupt
  API operations. A production restore should use a maintenance window or isolated
  recovery database, access controls, encrypted storage, and retention management.
- Related commit: `feat: add PostgreSQL backup and restore tooling`.
