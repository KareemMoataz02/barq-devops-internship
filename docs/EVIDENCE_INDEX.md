# Evidence and submission index

This index maps the repository, CI, and continuous screen recording to the assessment
requirements. Times refer to `BARQ_DevOps_Assessment_Kareem_Moataz.mp4` and use `MM:SS`.

## Submission coordinates

- **Repository:** [KareemMoataz02/barq-devops-internship](https://github.com/KareemMoataz02/barq-devops-internship)
- **Preserved starter tag:** [`starter-v2.0.0`](https://github.com/KareemMoataz02/barq-devops-internship/tree/starter-v2.0.0)
- **Starting video commit:** [`2590bb8`](https://github.com/KareemMoataz02/barq-devops-internship/commit/2590bb8)
- **Live application commit:** [`696dc88`](https://github.com/KareemMoataz02/barq-devops-internship/commit/696dc88)
- **Successful live-commit CI:** [GitHub Actions run 36181760571](https://github.com/KareemMoataz02/barq-devops-internship/actions/runs/36181760571)
- **Challenge receipt:** `a87d877c79d443489d22243349551007`, started at
  `2026-09-25T19:22:53.502585+00:00`
- **Recording file:** `BARQ_DevOps_Assessment_Kareem_Moataz.mp4`
- **Recording SHA-256:** `94aca69c60c2b5dae8e97c72c191e6e42b6feade4bd980c2a4f1c54fab320637`
- **Recording duration:** `42:33`
- **Shareable video:** [Google Drive recording](https://drive.google.com/file/d/1vXExEQTZk6CbymfLWH4bfZV0bF5EmLad/view?usp=sharing)
- **Final documentation commit and CI:** **Add after reviewing and pushing the final diff.**

The recording is continuous and unedited, but its 42:33 duration exceeds the requested
12–18 minute range. This deviation is recorded here rather than hidden.

## Progressive investigation and implementation

| Requirement | Repository evidence | Commit | Video evidence |
|---|---|---|---|
| Preserve the supplied baseline and history | Git history and `starter-v2.0.0` | [`8442da3`](https://github.com/KareemMoataz02/barq-devops-internship/commit/8442da3) | `00:40–01:40` repository, branch, starting commit, and clean status |
| Record and repair the broken baseline | [troubleshooting.md](../troubleshooting.md) | [`351c533`](https://github.com/KareemMoataz02/barq-devops-internship/commit/351c533) through [`d43fc2c`](https://github.com/KareemMoataz02/barq-devops-internship/commit/d43fc2c) | `01:40–02:40` architecture and repaired service configuration explanation |
| Correct health probes and health-gated startup | [docker-compose.yml](../docker-compose.yml) | [`6483864`](https://github.com/KareemMoataz02/barq-devops-internship/commit/6483864), [`b6b59c7`](https://github.com/KareemMoataz02/barq-devops-internship/commit/b6b59c7) | `02:40–04:35` build, start, wait, and healthy service list |
| Support SELinux-safe read-only mounts | Compose `:ro,Z` mounts and journal evidence | [`416461c`](https://github.com/KareemMoataz02/barq-devops-internship/commit/416461c) | `01:40–02:40` configuration explanation |
| Publish only NGINX and isolate data services | Loopback port plus frontend/internal-backend networks | [`6367153`](https://github.com/KareemMoataz02/barq-devops-internship/commit/6367153), [`96943d8`](https://github.com/KareemMoataz02/barq-devops-internship/commit/96943d8), [`b243d59`](https://github.com/KareemMoataz02/barq-devops-internship/commit/b243d59) | `04:05–04:35` service and port output; `23:30–23:55` validator network checks |
| Return distinct replica identities | `INSTANCE_ID` per application and NGINX upstreams | [`25493cf`](https://github.com/KareemMoataz02/barq-devops-internship/commit/25493cf) | `06:45–07:20` two starting identities; `35:00–40:30` final identity proof |
| Correct PostgreSQL and Redis connection settings | Runtime URLs and dependency-backed endpoints | [`d43fc2c`](https://github.com/KareemMoataz02/barq-devops-internship/commit/d43fc2c) | `05:45–06:45` `/ready`, `/records`, and `/counter` |
| Keep runtime credentials out of Git | [.env.example](../.env.example), [.gitignore](../.gitignore), and required interpolation | [`0692d57`](https://github.com/KareemMoataz02/barq-devops-internship/commit/0692d57) | `01:20–02:20` ignored environment and resolved configuration |
| Persist PostgreSQL and Redis data | Named volumes and Redis AOF | [`b9c817d`](https://github.com/KareemMoataz02/barq-devops-internship/commit/b9c817d) | `10:45–14:45` create marker, recreate containers, and retrieve marker |
| Run applications unprivileged under Gunicorn | [Dockerfile](../Dockerfile) | [`e11fe0d`](https://github.com/KareemMoataz02/barq-devops-internship/commit/e11fe0d) | `02:40–03:35` production image build |
| Bound service resources | CPU, memory, and PID ceilings in Compose | [`8f41bc4`](https://github.com/KareemMoataz02/barq-devops-internship/commit/8f41bc4) | `01:40–02:40` Compose design explanation |

## Validation, failure, persistence, logs, and CI

| Requirement | Repository evidence | Commit | Video evidence |
|---|---|---|---|
| Validate health, networks, ports, endpoints, dependencies, and identities | [validate.py](../validate.py) | [`50578d8`](https://github.com/KareemMoataz02/barq-devops-internship/commit/50578d8) | `15:30–15:55`, `23:30–23:55`, and `35:20–36:00` |
| Stop one backend, observe errors, recover, and prove service | [failure_test.py](../failure_test.py) and [troubleshooting.md](../troubleshooting.md) | [`3b85907`](https://github.com/KareemMoataz02/barq-devops-internship/commit/3b85907) | `07:15–10:15` manual failure and recovery; `15:55–16:10` automated test |
| Prove data survives recreation | Named volume configuration and marker lookup | [`b9c817d`](https://github.com/KareemMoataz02/barq-devops-internship/commit/b9c817d) | `10:45–14:45` |
| Create and restore a validated PostgreSQL backup | [backup.sh](../backup.sh), [restore.sh](../restore.sh), and completed drill | [`4efcb56`](https://github.com/KareemMoataz02/barq-devops-internship/commit/4efcb56) | Completed drill is documented in the repository; the recording focuses on recreation persistence |
| Analyze all supplied logs without double-counting | [scripts/analyze_logs.py](../scripts/analyze_logs.py) and [log_analysis.md](../log_analysis.md) | [`2cbe8c6`](https://github.com/KareemMoataz02/barq-devops-internship/commit/2cbe8c6) | `16:10–16:45` parser output and findings |
| Run clean-environment CI | [CI workflow](../.github/workflows/ci.yml) | [`91c7d44`](https://github.com/KareemMoataz02/barq-devops-internship/commit/91c7d44), [`c517ca0`](https://github.com/KareemMoataz02/barq-devops-internship/commit/c517ca0) | `41:25–42:25` live push; matching run linked above |

## Recorded challenge and final live changes

| Requirement | Repository or runtime evidence | Video evidence |
|---|---|---|
| Run the supplied challenge and retain its receipt | Local `.assessment/challenge.json`; receipt ID above | `17:30–17:50` |
| Diagnose and repair the injected fault without a full-stack reset | Live container and network inspection followed by the focused repair | `17:50–23:30` |
| Change the public endpoint from 8080 to 8090 | [docker-compose.yml](../docker-compose.yml), [.env.example](../.env.example), and [CI workflow](../.github/workflows/ci.yml) | `24:00–28:30` edit, restart, diff, and live port proof |
| Add `app-03` | [docker-compose.yml](../docker-compose.yml) and [nginx/nginx.conf](../nginx/nginx.conf) | `29:00–35:20` implementation and startup |
| Prove all three identities through NGINX | Repeated `/instance` requests and final validator | `35:20–40:30` |
| Review, commit, and push live changes | Live commit [`696dc88`](https://github.com/KareemMoataz02/barq-devops-internship/commit/696dc88) | `40:30–42:25` |

## Documentation and review artifacts

| Artifact | Evidence |
|---|---|
| Operating guide | [README.md](../README.md) |
| Investigation journal | [troubleshooting.md](../troubleshooting.md) |
| Decisions and trade-offs | [decisions.md](../decisions.md) |
| Security and production-readiness review | [security_review.md](../security_review.md) |
| Architecture diagram | [architecture.png](../architecture.png) and editable [architecture.excalidraw](../architecture.excalidraw) |
| AI disclosure | [AI_USAGE.md](../AI_USAGE.md) |

Before submission, replace the remaining bold placeholder above with the final
documentation commit and CI link.
