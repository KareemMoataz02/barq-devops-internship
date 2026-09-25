# Evidence and submission index

This is the pre-recording evidence map. Entries labelled **Pending video** must be replaced
with real timestamps after the single continuous recording. The final commit, matching CI
run, video URL, challenge receipt, third replica, and port 8090 do not exist yet and are not
claimed here.

## Submission coordinates

- **Repository:** [KareemMoataz02/barq-devops-internship](https://github.com/KareemMoataz02/barq-devops-internship)
- **Preserved starter tag:** [`starter-v2.0.0`](https://github.com/KareemMoataz02/barq-devops-internship/tree/starter-v2.0.0)
- **Final commit:** Pending video
- **Matching final CI run:** Pending video
- **Continuous 12-18 minute video URL:** Pending video
- **Challenge receipt ID:** Pending video; `.assessment/challenge.json` must be created by
  the first and only challenge run during recording
- **Starting video commit:** Pending video
- **Later documentation-only commits:** None at this pre-recording stage

## Investigation and repair evidence

| Requirement | File or output | Commit | Video timestamp |
|---|---|---|---|
| Preserve the supplied baseline and history | Git history and `starter-v2.0.0`; connection commit retains both supplied release commits | [`8442da3`](https://github.com/KareemMoataz02/barq-devops-internship/commit/8442da3) | **Pending video:** show starting log and tag |
| Record the broken baseline before fixes | [Initial startup evidence](../troubleshooting.md#2026-09-24--baseline-startup) with container state, logs, and failed public request | [`351c533`](https://github.com/KareemMoataz02/barq-devops-internship/commit/351c533) | **Pending video:** summarize what failed first |
| Correct the application health probe | [Healthcheck investigation and bounded retest](../troubleshooting.md#2026-09-24t1655547746270000--correct-the-application-health-probe) | [`6483864`](https://github.com/KareemMoataz02/barq-devops-internship/commit/6483864) | **Pending video:** explain `/healthz` 404 versus `/health` 200 |
| Make bind mounts work with SELinux | [Troubleshooting journal](../troubleshooting.md) and `:ro,Z` mounts in [docker-compose.yml](../docker-compose.yml) | [`416461c`](https://github.com/KareemMoataz02/barq-devops-internship/commit/416461c) | **Pending video:** mention failed mount hypothesis and fix |
| Publish the NGINX listener correctly | [docker-compose.yml](../docker-compose.yml) and [journal retest](../troubleshooting.md) | [`6367153`](https://github.com/KareemMoataz02/barq-devops-internship/commit/6367153) | **Pending video:** show only NGINX host binding |
| Restore proxy-to-app network reachability | Frontend memberships in [docker-compose.yml](../docker-compose.yml) and public health retest in [troubleshooting.md](../troubleshooting.md) | [`96943d8`](https://github.com/KareemMoataz02/barq-devops-internship/commit/96943d8) | **Pending video:** explain NGINX-to-app path |
| Return distinct replica identities | `INSTANCE_ID` values in [docker-compose.yml](../docker-compose.yml) and repeated `/instance` proof | [`25493cf`](https://github.com/KareemMoataz02/barq-devops-internship/commit/25493cf) | **Pending video:** show repeated `/instance` calls |
| Correct PostgreSQL and Redis connection settings | Runtime URLs in [docker-compose.yml](../docker-compose.yml) and `/ready`, `/records`, `/counter` retests in [troubleshooting.md](../troubleshooting.md) | [`d43fc2c`](https://github.com/KareemMoataz02/barq-devops-internship/commit/d43fc2c) | **Pending video:** run dependency-backed endpoints |
| Keep runtime credentials out of source and logs | [.env.example](../.env.example), [.gitignore](../.gitignore), required interpolation in [docker-compose.yml](../docker-compose.yml) | [`0692d57`](https://github.com/KareemMoataz02/barq-devops-internship/commit/0692d57) | **Pending video:** explain ignored local `.env` without showing its value |
| Isolate data services from host and proxy | Internal backend topology in [docker-compose.yml](../docker-compose.yml) and network proof in [troubleshooting.md](../troubleshooting.md) | [`b243d59`](https://github.com/KareemMoataz02/barq-devops-internship/commit/b243d59) | **Pending video:** show networks and prohibited ports |
| Persist PostgreSQL and Redis data | Named volumes and Redis AOF in [docker-compose.yml](../docker-compose.yml); recreation proof in [troubleshooting.md](../troubleshooting.md) | [`b9c817d`](https://github.com/KareemMoataz02/barq-devops-internship/commit/b9c817d) | **Pending video:** recreate app and PostgreSQL, then show the marker |
| Run the application unprivileged with a production server | [Dockerfile](../Dockerfile) and UID/GID runtime proof in [troubleshooting.md](../troubleshooting.md) | [`e11fe0d`](https://github.com/KareemMoataz02/barq-devops-internship/commit/e11fe0d) | **Pending video:** explain Gunicorn and UID 10001 |
| Gate startup on health and recover crashed processes | Health checks, `depends_on` conditions, and restart settings in [docker-compose.yml](../docker-compose.yml) | [`b6b59c7`](https://github.com/KareemMoataz02/barq-devops-internship/commit/b6b59c7) | **Pending video:** show all services healthy after startup |
| Bound service resource use | CPU, memory, and PID ceilings in [docker-compose.yml](../docker-compose.yml) with runtime inspection in [troubleshooting.md](../troubleshooting.md) | [`8f41bc4`](https://github.com/KareemMoataz02/barq-devops-internship/commit/8f41bc4) | **Pending video:** mention limits while showing Compose |

## Logs, validation, persistence, and CI evidence

| Requirement | File or output | Commit | Video timestamp |
|---|---|---|---|
| Keep supplied logs unchanged and analyze all three | [log_analysis.md](../log_analysis.md), [scripts/analyze_logs.py](../scripts/analyze_logs.py), and original files under [`logs/`](../logs/) | [`2cbe8c6`](https://github.com/KareemMoataz02/barq-devops-internship/commit/2cbe8c6) | **Pending video:** reproduce one historical finding |
| Avoid double-counting and answer every log question | Exact-source-line deduplication, malformed-line counts, retry correlations, timeline, and all ten answers in [log_analysis.md](../log_analysis.md) | [`2cbe8c6`](https://github.com/KareemMoataz02/barq-devops-internship/commit/2cbe8c6) | **Pending video:** show 720 unique requests and one request-ID correlation |
| Validate public access, endpoints, dependencies, identities, networks, and ports | [validate.py](../validate.py), documented PASS/FAIL behavior in [README.md](../README.md#run-automated-checks) | [`50578d8`](https://github.com/KareemMoataz02/barq-devops-internship/commit/50578d8) | **Pending video:** run validator before and after live changes |
| Stop one backend, measure errors, restore it, and prove recovery | [failure_test.py](../failure_test.py) and measured 29-success/31-error run in [troubleshooting.md](../troubleshooting.md) | [`3b85907`](https://github.com/KareemMoataz02/barq-devops-internship/commit/3b85907) | **Pending video:** run the failure test and show recovered identity |
| Create, validate, and restore a real PostgreSQL backup | [backup.sh](../backup.sh), [restore.sh](../restore.sh), and marker-based restore drill in [troubleshooting.md](../troubleshooting.md) | [`4efcb56`](https://github.com/KareemMoataz02/barq-devops-internship/commit/4efcb56) | **Pending video:** explain the completed restore proof |
| Run a full clean-environment CI pipeline | [CI workflow](../.github/workflows/ci.yml) and successful build/test/start/validate/cleanup runs | [`91c7d44`](https://github.com/KareemMoataz02/barq-devops-internship/commit/91c7d44), [`c517ca0`](https://github.com/KareemMoataz02/barq-devops-internship/commit/c517ca0) | **Pending video:** show matching final run after live push |

## Documentation and review evidence

| Requirement | File or output | Commit | Video timestamp |
|---|---|---|---|
| Copyable setup, build, start, stop, test, failure, backup, restore, and cleanup | [README.md](../README.md) | [`ad43cdf`](https://github.com/KareemMoataz02/barq-devops-internship/commit/ad43cdf) | **Pending video:** use the documented commands during demonstration |
| Investigation journal with hypotheses, failed attempts, fixes, and retests | [troubleshooting.md](../troubleshooting.md) | Progressive commits beginning with [`351c533`](https://github.com/KareemMoataz02/barq-devops-internship/commit/351c533) | **Pending video:** explain one failed attempt and its lesson |
| Decisions, assumptions, alternatives, trade-offs, and limitations | [decisions.md](../decisions.md) | [`80918c0`](https://github.com/KareemMoataz02/barq-devops-internship/commit/80918c0) | **Pending video:** explain proxy retry and timeout choice |
| At least eight security and production-readiness findings | [security_review.md](../security_review.md) | [`33991c0`](https://github.com/KareemMoataz02/barq-devops-internship/commit/33991c0) | **Pending video:** distinguish implemented controls from production plans |
| Diagram request flow, ports, networks, storage, and health relationships | [architecture.png](../architecture.png) and editable [architecture.excalidraw](../architecture.excalidraw) | [`4ec95bc`](https://github.com/KareemMoataz02/barq-devops-internship/commit/4ec95bc) | **Pending video:** show diagram; update after live topology change |
| Disclose assisted work and independent verification | [AI_USAGE.md](../AI_USAGE.md) | Pending; deferred before recording | **Pending video:** explain tools, changes, and verification honestly |

## Recorded challenge and final-state evidence

| Requirement | File or output | Commit | Video timestamp |
|---|---|---|---|
| Show repository, starting commit, and clean status | Terminal output in continuous recording | Pending video | **Pending video** |
| Build/start the stopped environment and show health | Compose build, start, and `ps` output in continuous recording | Pending video | **Pending video** |
| Exercise `/`, `/health`, `/ready`, `/records`, `/counter`, and both initial identities | Live HTTP output in continuous recording | Pending video | **Pending video** |
| Show a record survive application and PostgreSQL recreation | Marker creation, targeted recreation, and post-recreation lookup | Pending video | **Pending video** |
| Run the supplied challenge exactly once and retain its receipt | `.assessment/challenge.json` plus continuous terminal output | Pending video | **Pending video** |
| Diagnose and repair the injected runtime fault without resetting the stack | Live diagnosis, focused diff, retest, and challenge verification | Pending video | **Pending video** |
| Change the public port to 8090 | Final [docker-compose.yml](../docker-compose.yml), live HTTP proof, and validation | Pending video | **Pending video** |
| Add `app-03` and prove all three identities | Final [docker-compose.yml](../docker-compose.yml), [nginx/nginx.conf](../nginx/nginx.conf), repeated `/instance`, and validation | Pending video | **Pending video** |
| Review, commit, and push live changes | Clean status, diff, commit hashes, push output, and matching CI run | Pending video | **Pending video** |
| Match every final artifact to three replicas on port 8090 | Final README, diagram, reports, evidence index, GitHub commit, CI run, and video | Pending video | **Pending video** |

## Finalization checklist

After recording, update this file with the actual starting commit, challenge receipt ID,
live change commits, final commit, matching CI URL, accessible video URL, and exact video
timestamps. Update `README.md`, `architecture.png`, `architecture.excalidraw`, decisions,
and any affected review text so every artifact describes three application instances on
port 8090. List any later documentation-only commits explicitly and link their CI runs.
