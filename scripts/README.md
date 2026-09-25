# Automation scripts

The implemented operator scripts live at the repository root:

| Script | Purpose |
|---|---|
| [`validate.py`](../validate.py) | Validate Compose health, network isolation, host-port exposure, public endpoints, real dependencies, and every app identity. |
| [`failure_test.py`](../failure_test.py) | Stop one labelled application replica, measure availability and errors, restore it safely, and prove it serves again. |
| [`backup.sh`](../backup.sh) | Create and validate a restricted custom-format PostgreSQL dump. |
| [`restore.sh`](../restore.sh) | Validate and transactionally restore an explicit dump, then verify restored records. |
| [`analyze_logs.py`](analyze_logs.py) | Parse, validate, deduplicate, and correlate all three supplied historical logs. |

The scripts use bounded waits, useful PASS/FAIL output, non-zero failure exits, exact
Compose project/service labels, and cleanup paths. Usage examples are in
[README.md](../README.md).

[`video_challenge.py`](video_challenge.py) and [`../video_challenge.sh`](../video_challenge.sh)
are unchanged supplied exercise tools. Run the wrapper once, for the first time during the
continuous recording, and never delete its one-run state to retry.
