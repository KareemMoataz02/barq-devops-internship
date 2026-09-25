# Log analysis

## Method and source integrity

I treated `access.log` as the source of the final response seen by the client.
`error.log` can contain multiple upstream attempts for one request, and
`application.log` can contain both a dependency error and an HTTP completion event
for the same request. Counting either of those files as client requests would inflate
the denominator.

The supplied files were analyzed without modification. Their SHA-256 hashes are:

| File | SHA-256 |
|---|---|
| `logs/access.log` | `f8562d6ee86b7e7aa67e8c3474ca16eca8a1e5f521f78f3808d784be62efa754` |
| `logs/error.log` | `940588d00bafd6c5c7cad8a4d8a0c39b665d1fd64928d93a5d1f1810c3c6f175` |
| `logs/application.log` | `483d06cf431faa1d04a7264b015798bcde4bed1ba618f87426e79fb0d5caea05` |

The reproducible analyzer uses Python's standard library. Run it from the repository
root:

```bash
sha256sum logs/access.log logs/error.log logs/application.log
wc -l -c logs/access.log logs/error.log logs/application.log
./scripts/analyze_logs.py
rg -n 'lab-000122|lab-000124|lab-000292|lab-000630' logs
```

The analyzer parses both NDJSON files, validates the NGINX error-line format,
removes exact duplicate lines, groups access rows by `request_id`, and refuses to
aggregate if one ID has conflicting access rows. The full implementation is in
[`scripts/analyze_logs.py`](scripts/analyze_logs.py).

## 1. Interval and file quality

The combined UTC interval is **2026-08-20 11:00:00.015Z through 11:30:00Z**.
Access and application events end at 11:29:57.578Z; the final error-log line at
11:30:00Z is a rotation notice.

| File | Event interval (UTC) | Physical lines | Valid lines | Malformed | Exact duplicate groups | Extra duplicate lines | Unique valid lines |
|---|---|---:|---:|---:|---:|---:|---:|
| `access.log` | 11:00:00.015–11:29:57.578 | 726 | 725 | 1 (line 311) | 5 | 5 | 720 |
| `error.log` | 11:05:02–11:30:00 | 68 | 68 | 0 | 0 | 0 | 68 |
| `application.log` | 11:00:00.015–11:29:57.578 | 730 | 729 | 1 (line 401) | 2 | 2 | 727 |

“Valid lines” includes duplicate physical lines. “Extra duplicate lines” counts the
second copy in each duplicate group, so access has five groups involving ten physical
lines but only five excess copies. After exact deduplication, the application log has
680 HTTP events and 47 additional `dependency_error` events.

## 2. Distinct client requests and deduplication

There are **720 distinct client requests**, with request IDs `lab-000001` through
`lab-000720`. After excluding the malformed line and removing exact copies, every
access request ID has exactly one row.

The access row already records the complete upstream attempt list. For example,
`lab-000124` contains upstream statuses `502, 200`; that is one client request with
two upstream attempts, not two client requests. I therefore count one deduplicated
access row per request ID. I use the other logs only to explain that final outcome.

## 3. Final client statuses and error rate

| Final status | Requests | Share of 720 |
|---:|---:|---:|
| 200 | 615 | 85.42% |
| 404 | 10 | 1.39% |
| 502 | 40 | 5.56% |
| 503 | 47 | 6.53% |
| 504 | 8 | 1.11% |

The client-visible **server error rate is 95 / 720 = 13.19%**, where the numerator
is all final 5xx responses and the denominator is all distinct client requests. The
broader non-2xx rate is **105 / 720 = 14.58%**; its additional ten responses are
expected `/missing` 404 checks rather than server failures.

## 4. Failure paths, windows, and backends

Correlation of successful single-upstream requests proves that
`172.23.0.11:8080` is app-01 and `172.23.0.12:8080` is app-02.

| Window (UTC) | Client result | Path distribution | Backend evidence | Finding |
|---|---:|---|---|---|
| 11:05:02–11:09:57 | 40 × 502 | 10 each on `/`, `/health`, `/records`, `/counter` | All final failures target app-02; error log has 59 refused connections to app-02 | app-02 was unreachable. Nineteen other requests retried app-01 and succeeded. |
| 11:12:09.524–11:15:52.024 | 31 × 503 | `/ready` 15, `/counter` 16 | app-01 has 15 and app-02 has 16 Redis errors | Both apps report `redis` `TimeoutError`; this is a shared dependency incident. |
| 11:20:07.540–11:21:45.040 | 16 × 503 | `/ready` 8, `/records` 8 | Eight failures on each app | Both apps report PostgreSQL `InvalidPassword`; this is a shared configuration/dependency failure. |
| 11:25:14–11:26:47 | 8 × 504 | `/records` 8 | Four timeouts on each app | NGINX times out at 2.001 s; each app later logs 200 after 2.700 s. |

The remaining final failure distribution is:

| Path | 502 | 503 | 504 | Total 5xx |
|---|---:|---:|---:|---:|
| `/` | 10 | 0 | 0 | 10 |
| `/health` | 10 | 0 | 0 | 10 |
| `/ready` | 0 | 23 | 0 | 23 |
| `/records` | 10 | 8 | 8 | 26 |
| `/counter` | 10 | 16 | 0 | 26 |

The ten `/missing` 404s are distributed through the whole interval and are not part
of these incidents.

## 5. Client latency

For all 720 distinct client requests, the median NGINX `request_time` is **54 ms**
and p95 is **2,001 ms**.

The median is the arithmetic mean of sorted positions 360 and 361; both are 54 ms.
For p95 I use nearest-rank: `ceil(0.95 × 720) = 684`, so the 684th sorted observation
is 2.001 seconds. Results include successful and failed client responses because the
question concerns experienced client latency. The p95 aligns with the proxy timeout
responses rather than normal application latency.

## 6. Upstream retries

NGINX retried **19 requests**, and **all 19 ultimately returned 200**. Each first
attempt targeted app-02 and returned 502; each second attempt reached app-01 and
returned 200.

The request IDs are:

```text
lab-000124, lab-000130, lab-000136, lab-000142, lab-000148,
lab-000154, lab-000160, lab-000166, lab-000172, lab-000178,
lab-000184, lab-000190, lab-000196, lab-000202, lab-000208,
lab-000214, lab-000220, lab-000226, lab-000232
```

These are counted once each in the 720-request denominator and once each in the 615
final 200 responses. The 59 connection-refused error lines comprise these 19 recovered
attempts plus the 40 final 502 requests.

## 7. Incident timeline across all three logs

| Time (UTC) | Evidence and interpretation |
|---|---|
| 11:00:00.015 | Access and application logs begin with normal responses, including the intentional `/missing` 404. |
| 11:05:02 | The error log first reports connection refused to `172.23.0.12:8080`; access request `lab-000122` returns 502 and has no application event. This is the first operational failure. |
| 11:05:07–11:09:37 | Nineteen access rows show `502, 200`; the error log records failed app-02 attempts while application logs show the same IDs completing on app-01. |
| 11:09:57 | Last final 502. The error log contains 59 connection-refused attempts across the interval. |
| 11:10:02.532 | `lab-000242` reaches app-02 directly and returns 200, providing the first observed recovery evidence for that backend. |
| 11:12:09.524 | Application log first reports Redis `TimeoutError`; its paired access response is 503. Both apps continue reporting the dependency failure. |
| 11:15:52.024 | Last Redis dependency error. |
| 11:16:07.534 | `/ready` returns 200 through app-02, the first observed dependency recovery check. |
| 11:20:07.540 | Application log first reports PostgreSQL `InvalidPassword`; paired access responses are 503 across both apps. |
| 11:21:45.040 | Last PostgreSQL authentication error. |
| 11:22:07.582 | `/ready` returns 200, providing the first observed recovery evidence after the PostgreSQL incident. |
| 11:25:14–11:26:47 | Error log records eight `/records` upstream timeouts. Access returns 504 at 2.001 s, while application logs later report 200 at 2.700 s on both apps. |
| 11:27:12.576 | `/records` returns 200 in 76 ms, providing the first observed recovery evidence after the latency incident. |
| 11:29:57.578 | Final access and application event is a successful request. |
| 11:30:00 | Error log reports stream rotation; this is a notice, not an incident. |

## 8. Correlated examples

### Failed dependency request: `lab-000292`

- Application at **11:12:09.524Z**: app-02 emits `dependency_error`, dependency
  `redis`, error type `TimeoutError`.
- Application at **11:12:09.525Z**: app-02 finishes `/ready` with status 503 and
  duration 2,025 ms.
- Access at **11:12:09.525Z**: the client receives 503 from
  `172.23.0.12:8080` in 2.025 seconds.

The matching ID, instance/IP mapping, path, status, timestamp, and duration show that
the client failure came from an application-reported Redis failure.

### Successful request after retry: `lab-000124`

- Error at **11:05:07Z**: connection to app-02 at `172.23.0.12:8080` is refused.
- Application at **11:05:07.620Z**: app-01 completes `/ready` with 200.
- Access at **11:05:07.620Z**: upstreams are app-02 then app-01, upstream statuses
  are `502, 200`, and the final client status is 200 in 120 ms.

This is one client request with two upstream attempts. It demonstrates both the
app-02 connectivity fault and successful retry behavior without double-counting.

An additional proxy-failure example is `lab-000122`: the error log records connection
refused to app-02 at 11:05:02Z, access returns 502 at 11:05:02.503Z, and no matching
application event exists because the request never reached Flask.

## 9. Proxy/connectivity versus dependency/application errors

- **Connectivity:** all 59 `connect() failed (111: Connection refused)` lines target
  app-02. Forty IDs finish as 502 and have no application event; 19 succeed only after
  retrying app-01. That absence/presence pattern proves the original attempt failed
  before Flask handled it.
- **Application dependencies:** all 47 final 503 requests have matching application
  `dependency_error` and `http_request` events. Redis accounts for 31 `TimeoutError`
  events, and PostgreSQL accounts for 16 `InvalidPassword` events. Both app instances
  are affected, which argues against a single app-container outage.
- **Timeout boundary:** the eight 504 responses are proxy timeouts caused by slow
  upstream completion. NGINX stops waiting at 2.001 seconds, while Flask logs the same
  IDs as 200 after 2.700 seconds. The application completed work, but too late for the
  client. The logs do not identify why `/records` became slow.

## 10. Limits and next checks

These historical logs prove client outcomes and correlations, but they do not prove
why app-02 refused connections, what caused the Redis timeouts, why the PostgreSQL
password was invalid, or why database reads took 2.7 seconds. They contain no Docker
events, health history, restart/OOM state, resource metrics, dependency logs, database
query plans, network packet evidence, or configuration-change audit trail. One
synthetic client IP also cannot establish real traffic diversity or production load.

In a running incident I would next check:

1. container health, restart count, exit/OOM state, and Docker events for app-02;
2. NGINX DNS/upstream resolution and network reachability from the NGINX namespace;
3. Redis and PostgreSQL server logs, health, connection counts, and latency;
4. application configuration sources and secret versions without printing values;
5. CPU, memory, disk, connection-pool, lock, and slow-query metrics around each window;
6. traces or structured span timing using the existing request IDs.

The original malformed lines cannot be reconstructed safely, and internal container
IP addresses are historical identifiers rather than stable service identities.
