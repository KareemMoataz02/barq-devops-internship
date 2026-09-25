#!/usr/bin/env bash
set -euo pipefail

project="barq-assessment"
output=""

usage() {
  cat <<'EOF'
Usage: ./backup.sh [--project NAME] [--output FILE]

Create a validated custom-format PostgreSQL dump from the selected Compose project.
EOF
}

while (($#)); do
  case "$1" in
    --project)
      [[ $# -ge 2 ]] || { echo "FAIL: --project requires a value" >&2; exit 1; }
      project="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || { echo "FAIL: --output requires a value" >&2; exit 1; }
      output="$2"
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

if [[ -z "$output" ]]; then
  output="backups/barq-$(date -u +%Y%m%dT%H%M%SZ).dump"
fi

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

output_dir="$(dirname -- "$output")"
output_name="$(basename -- "$output")"
mkdir -p -- "$output_dir"
temporary_output="$(mktemp "$output_dir/.${output_name}.tmp.XXXXXX")"
container_dump="/tmp/barq-backup-$$.dump"

cleanup() {
  docker exec "$container_id" rm -f -- "$container_dump" >/dev/null 2>&1 || true
  rm -f -- "$temporary_output"
}
trap cleanup EXIT

# Variables in this block intentionally expand inside the PostgreSQL container.
# shellcheck disable=SC2016
timeout 60 docker exec "$container_id" sh -ceu '
  pg_dump \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --no-owner \
    --no-privileges \
    --file="$1"
  pg_restore --list "$1" >/dev/null
' -- "$container_dump"

docker cp "$container_id:$container_dump" "$temporary_output" >/dev/null
[[ -s "$temporary_output" ]] || {
  echo "FAIL: PostgreSQL produced an empty backup" >&2
  exit 1
}
chmod 600 "$temporary_output"
mv -f -- "$temporary_output" "$output"

bytes="$(wc -c < "$output")"
checksum="$(sha256sum "$output" | awk '{print $1}')"
echo "PASS: PostgreSQL backup written to $output"
echo "PASS: custom-format dump validated (${bytes} bytes, sha256=$checksum)"
