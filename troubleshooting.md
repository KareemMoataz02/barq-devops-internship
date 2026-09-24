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
