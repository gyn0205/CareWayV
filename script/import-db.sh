#!/usr/bin/env bash
# Restore the shared PostgreSQL snapshot into this checkout's Compose database.
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: bash script/import-db.sh [path/to/snapshot.dump]

Imports data/carewayv.dump by default. Requires Docker with Compose v2.
Creates .env from .env.example if missing and starts the db service.
Replaces tables contained in the snapshot, including their existing data.
Saves the previous database to data/backups/ before importing.
EOF
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
[[ $# -le 1 ]] || { usage >&2; exit 1; }
DUMP_FILE="${1:-$ROOT_DIR/data/carewayv.dump}"
[[ -r "$DUMP_FILE" && -s "$DUMP_FILE" ]] || fail "Snapshot missing, empty or unreadable: $DUMP_FILE"
command -v docker >/dev/null 2>&1 || fail 'Install Docker and Docker Compose v2 first.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 is required.'
docker info >/dev/null 2>&1 || fail 'Docker is unavailable. Start Docker Desktop / Docker Engine.'

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  [[ -f "$ROOT_DIR/.env.example" ]] || fail "Missing $ROOT_DIR/.env.example"
  (umask 077; cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env")
  printf 'Created .env from .env.example.\n'
fi

compose=(docker compose --project-directory "$ROOT_DIR" --env-file "$ROOT_DIR/.env" -f "$ROOT_DIR/compose.yaml")
printf 'Starting PostgreSQL...\n'
"${compose[@]}" up -d --wait --wait-timeout 90 db

# Reject files pg_restore cannot recognize before backing up or changing the DB.
"${compose[@]}" exec -T db pg_restore --list < "$DUMP_FILE" > /dev/null

BACKUP_DIR="$ROOT_DIR/data/backups"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/before-import-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
PARTIAL_BACKUP="$BACKUP_FILE.partial"
trap 'if [[ -n "${PARTIAL_BACKUP:-}" ]]; then rm -f -- "$PARTIAL_BACKUP"; fi' EXIT
printf 'Backing up the current database...\n'
(
  umask 077
  "${compose[@]}" exec -T db sh -eu -c '
    exec pg_dump --format=custom --no-owner --no-privileges \
      -U "$POSTGRES_USER" -d "$POSTGRES_DB"
  ' > "$PARTIAL_BACKUP"
)
[[ -s "$PARTIAL_BACKUP" ]] || fail 'Database backup is empty; import cancelled.'
mv -- "$PARTIAL_BACKUP" "$BACKUP_FILE"
PARTIAL_BACKUP=''
printf 'Backup: %s\n' "$BACKUP_FILE"

printf 'Importing: %s\n' "$DUMP_FILE"
# One transaction includes both DROP and CREATE/COPY. An error rolls it all back.
if ! "${compose[@]}" exec -T db sh -eu -c '
  exec pg_restore --clean --if-exists --no-owner --no-privileges \
    --single-transaction --exit-on-error \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' < "$DUMP_FILE"; then
  fail "Import failed; the restore transaction was rolled back. Backup: $BACKUP_FILE"
fi

printf 'Import completed. Database migration revision:\n'
"${compose[@]}" exec -T db sh -eu -c '
  exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT version_num FROM alembic_version;"
'
