#!/usr/bin/env bash
set -euo pipefail

APP_NAME="multi-agents"
PROJECT_DIR="/opt/multi-agents"
OUTPUT_DIR="/opt/backups/multi-agents"
INCLUDE_ENV="false"
ARCHIVE_NAME=""

usage() {
  cat <<'USAGE'
Usage:
  sudo bash scripts/server_backup.sh [options]

Options:
  --project-dir PATH       Project directory. Default: /opt/multi-agents
  --output-dir PATH        Backup output directory. Default: /opt/backups/multi-agents
  --include-env            Include backend/.env in the archive. Disabled by default.
  --name NAME.tar.gz       Archive file name. Default: multi-agents-backup-YYYYmmdd-HHMMSS.tar.gz
  -h, --help               Show help.

Examples:
  sudo bash scripts/server_backup.sh
  sudo bash scripts/server_backup.sh --include-env
  sudo bash scripts/server_backup.sh --output-dir /backups/multi-agents
USAGE
}

log() {
  printf '[%s] %s\n' "$(date +'%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

read_env_value() {
  local env_file="$1"
  local key="$2"

  python3 - "$env_file" "$key" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]

if not path.exists():
    sys.exit(0)

pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=\s*(.*)\s*$")

for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue

    match = pattern.match(raw_line)
    if not match:
        continue

    value = match.group(1).strip()

    if value and value[0] not in ("'", '"') and " #" in value:
        value = value.split(" #", 1)[0].strip()

    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]

    print(value)
    sys.exit(0)
PY
}

normalize_postgres_url() {
  local url="$1"
  url="${url/#postgresql+asyncpg:\/\//postgresql://}"
  url="${url/#postgres+asyncpg:\/\//postgresql://}"
  url="${url/#postgres:\/\//postgresql://}"
  printf '%s' "$url"
}

json_escape() {
  python3 - "$1" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1], ensure_ascii=False))
PY
}

copy_if_exists() {
  local src="$1"
  local dst="$2"

  if [ -e "$src" ]; then
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst"
    return 0
  fi

  return 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="${2:-}"
      [ -n "$PROJECT_DIR" ] || die "--project-dir requires a value"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      [ -n "$OUTPUT_DIR" ] || die "--output-dir requires a value"
      shift 2
      ;;
    --include-env)
      INCLUDE_ENV="true"
      shift
      ;;
    --name)
      ARCHIVE_NAME="${2:-}"
      [ -n "$ARCHIVE_NAME" ] || die "--name requires a value"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

require_cmd python3
require_cmd tar
require_cmd sha256sum
require_cmd pg_dump
require_cmd redis-cli

[ -d "$PROJECT_DIR" ] || die "Project directory not found: $PROJECT_DIR"
ENV_FILE="$PROJECT_DIR/backend/.env"
[ -f "$ENV_FILE" ] || die "backend/.env not found: $ENV_FILE"

DATABASE_URL="$(read_env_value "$ENV_FILE" DATABASE_URL)"
REDIS_URL="$(read_env_value "$ENV_FILE" REDIS_URL)"

[ -n "$DATABASE_URL" ] || die "DATABASE_URL is missing in $ENV_FILE"
[ -n "$REDIS_URL" ] || REDIS_URL="redis://localhost:6379/0"

PG_DUMP_URL="$(normalize_postgres_url "$DATABASE_URL")"

TIMESTAMP="$(date +'%Y%m%d-%H%M%S')"
[ -n "$ARCHIVE_NAME" ] || ARCHIVE_NAME="${APP_NAME}-backup-${TIMESTAMP}.tar.gz"
[[ "$ARCHIVE_NAME" == *.tar.gz ]] || die "--name must end with .tar.gz"

BACKUP_ROOT="${OUTPUT_DIR%/}"
ARCHIVE_PATH="$BACKUP_ROOT/$ARCHIVE_NAME"
WORK_PARENT="$(mktemp -d)"
WORK_DIR="$WORK_PARENT/${ARCHIVE_NAME%.tar.gz}"

cleanup() {
  rm -rf "$WORK_PARENT"
}
trap cleanup EXIT

mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"

mkdir -p "$WORK_DIR/config/nginx" "$WORK_DIR/config/systemd"

log "Backing up PostgreSQL with pg_dump -Fc..."
pg_dump "$PG_DUMP_URL" -Fc -f "$WORK_DIR/postgres.dump"

log "Backing up Redis RDB snapshot..."
if redis-cli -u "$REDIS_URL" BGSAVE >/tmp/${APP_NAME}-redis-bgsave.$$ 2>&1; then
  :
else
  if grep -q "Background save already in progress" /tmp/${APP_NAME}-redis-bgsave.$$; then
    log "Redis BGSAVE already in progress; waiting for it to finish..."
  else
    cat /tmp/${APP_NAME}-redis-bgsave.$$ >&2 || true
    rm -f /tmp/${APP_NAME}-redis-bgsave.$$
    die "Redis BGSAVE failed"
  fi
fi
rm -f /tmp/${APP_NAME}-redis-bgsave.$$

for _ in $(seq 1 60); do
  IN_PROGRESS="$(redis-cli -u "$REDIS_URL" --raw INFO persistence | awk -F: '/^rdb_bgsave_in_progress:/ {gsub(/\r/, "", $2); print $2}')"
  [ "${IN_PROGRESS:-0}" = "0" ] && break
  sleep 1
done

IN_PROGRESS="$(redis-cli -u "$REDIS_URL" --raw INFO persistence | awk -F: '/^rdb_bgsave_in_progress:/ {gsub(/\r/, "", $2); print $2}')"
[ "${IN_PROGRESS:-0}" = "0" ] || die "Timed out waiting for Redis BGSAVE"

REDIS_DIR="$(redis-cli -u "$REDIS_URL" --raw CONFIG GET dir | tail -n 1)"
REDIS_DBFILENAME="$(redis-cli -u "$REDIS_URL" --raw CONFIG GET dbfilename | tail -n 1)"
[ -n "$REDIS_DIR" ] || die "Could not determine Redis dir"
[ -n "$REDIS_DBFILENAME" ] || REDIS_DBFILENAME="dump.rdb"

cp "${REDIS_DIR%/}/${REDIS_DBFILENAME}" "$WORK_DIR/redis.rdb"

log "Collecting Nginx and systemd config..."
copy_if_exists /etc/nginx/nginx.conf "$WORK_DIR/config/nginx/nginx.conf" || true

if [ -d /etc/nginx/sites-enabled ]; then
  mkdir -p "$WORK_DIR/config/nginx/sites-enabled"
  cp -a /etc/nginx/sites-enabled/. "$WORK_DIR/config/nginx/sites-enabled/" 2>/dev/null || true
fi

if [ -d /etc/nginx/conf.d ]; then
  mkdir -p "$WORK_DIR/config/nginx/conf.d"
  cp -a /etc/nginx/conf.d/. "$WORK_DIR/config/nginx/conf.d/" 2>/dev/null || true
fi

copy_if_exists /etc/systemd/system/multi-agents-backend.service "$WORK_DIR/config/systemd/multi-agents-backend.service" || true

if [ "$INCLUDE_ENV" = "true" ]; then
  log "WARNING: --include-env enabled. backend/.env may contain API keys and database credentials."
  cp "$ENV_FILE" "$WORK_DIR/config/backend.env"
  chmod 600 "$WORK_DIR/config/backend.env"
fi

log "Writing manifest and checksums..."
GIT_COMMIT="$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || printf 'unknown')"
HOSTNAME_VALUE="$(hostname)"

cat > "$WORK_DIR/manifest.json" <<EOF
{
  "app": $(json_escape "$APP_NAME"),
  "created_at": $(json_escape "$(date -Iseconds)"),
  "hostname": $(json_escape "$HOSTNAME_VALUE"),
  "project_dir": $(json_escape "$PROJECT_DIR"),
  "git_commit": $(json_escape "$GIT_COMMIT"),
  "include_env": $INCLUDE_ENV,
  "contains_postgres": true,
  "contains_redis": true,
  "contains_nginx_config": true,
  "contains_systemd_config": true,
  "archive_name": $(json_escape "$ARCHIVE_NAME")
}
EOF

(
  cd "$WORK_DIR"
  find . -type f -print0 | sort -z | xargs -0 sha256sum > checksums.sha256
)

log "Creating archive..."
tar -C "$WORK_PARENT" -czf "$ARCHIVE_PATH" "$(basename "$WORK_DIR")"
chmod 600 "$ARCHIVE_PATH"
sha256sum "$ARCHIVE_PATH" > "$ARCHIVE_PATH.sha256"
chmod 600 "$ARCHIVE_PATH.sha256"

log "Backup completed:"
printf '%s\n' "$ARCHIVE_PATH"
printf '%s\n' "$ARCHIVE_PATH.sha256"

if [ "$INCLUDE_ENV" = "false" ]; then
  log "backend/.env was NOT included. Save it separately, or rerun with --include-env if you accept the risk."
fi
