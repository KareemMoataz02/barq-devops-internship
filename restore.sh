#!/usr/bin/env bash
set -euo pipefail

project="barq-assessment"
input=""

usage() {
  cat <<'EOF'
Usage: ./restore.sh --input FILE [--project NAME]

Validate and restore a custom-format dump into the selected Compose PostgreSQL service.
Existing database objects represented in the dump are replaced.
EOF
}

while (($#)); do
  case "$1" in
    --project)
      [[ $# -ge 2 ]] || { echo "FAIL: --project requires a value" >&2; exit 1; }
      project="$2"
      shift 2
      ;;
    --input)
      [[ $# -ge 2 ]] || { echo "FAIL: --input requires a value" >&2; exit 1; }
      input="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "FAIL: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

[[ "$project" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || {
  echo "FAIL: invalid Compose project name" >&2
  exit 1
}
[[ -n "$input" ]] || {
  echo "FAIL: --input is required" >&2
  usage >&2
  exit 1
}
[[ -f "$input" && -r "$input" && -s "$input" ]] || {
  echo "FAIL: backup must be a readable, non-empty regular file" >&2
  exit 1
}

mapfile -t containers < <(
  docker ps -aq \
    --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.service=postgres"
)
[[ ${#containers[@]} -eq 1 ]] || {
  echo "FAIL: expected one $project/postgres container, found ${#containers[@]}" >&2
  exit 1
}
container_id="${containers[0]}"

read -r running health < <(
  docker inspect --format '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id"
)
[[ "$running" == "true" && "$health" == "healthy" ]] || {
  echo "FAIL: $project/postgres must be running and healthy" >&2
  exit 1
}

container_dump="/tmp/barq-restore-$$.dump"
cleanup() {
  docker exec "$container_id" rm -f -- "$container_dump" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker cp "$input" "$container_id:$container_dump" >/dev/null
timeout 30 docker exec "$container_id" pg_restore --list "$container_dump" >/dev/null
echo "PASS: backup archive is readable"

# Variables in this block intentionally expand inside the PostgreSQL container.
# shellcheck disable=SC2016
timeout 120 docker exec "$container_id" sh -ceu '
  pg_restore \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    --exit-on-error \
    --single-transaction \
    "$1"
' -- "$container_dump"

record_count="$(
  # Variables in this block intentionally expand inside the PostgreSQL container.
  # shellcheck disable=SC2016
  timeout 15 docker exec "$container_id" sh -ceu '
    psql \
      --username="$POSTGRES_USER" \
      --dbname="$POSTGRES_DB" \
      --tuples-only \
      --no-align \
      --command="SELECT count(*) FROM records"
  '
)"
[[ "$record_count" =~ ^[0-9]+$ ]] || {
  echo "FAIL: restored records table could not be verified" >&2
  exit 1
}

echo "PASS: PostgreSQL restore completed from $input"
echo "PASS: restored records table contains $record_count rows"
