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
