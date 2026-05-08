#!/usr/bin/env bash
set -euo pipefail

# multi-agents ECS local backup script
# - Backup PostgreSQL (pg_dump -Fc)
# - Backup Redis snapshot
# - Backup nginx/systemd config
# - Optional backup backend/.env via --include-env

PROJECT_DIR="/opt/multi-agents"
OUTPUT_DIR="/opt/backups/multi-agents"
INCLUDE_ENV=0
ARCHIVE_NAME=""

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<EOF
Usage:
  ${SCRIPT_NAME} [options]

Options:
  --project-dir PATH     Project root directory (default: /opt/multi-agents)
  --output-dir PATH      Backup output directory (default: /opt/backups/multi-agents)
  --include-env          Include backend/.env in backup package (WARNING: sensitive data)
  --name NAME.tar.gz     Custom archive filename
  -h, --help             Show this help

Examples:
  ${SCRIPT_NAME}
  ${SCRIPT_NAME} --include-env
  ${SCRIPT_NAME} --output-dir /data/backups --name multi-agents-backup-custom.tar.gz
EOF
}

log() {
  echo "[backup] $*"
}

warn() {
  echo "[backup][WARN] $*" >&2
}

err() {
  echo "[backup][ERROR] $*" >&2
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    err "Missing required command: $1"
    exit 1
  }
}

trim() {
  local s="$1"
  s="$(echo "$s" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  printf "%s" "$s"
}

strip_quotes() {
  local s="$1"
  if [[ ${#s} -ge 2 && "${s:0:1}" == "\"" && "${s: -1}" == "\"" ]]; then
    s="${s:1:${#s}-2}"
  elif [[ ${#s} -ge 2 && "${s:0:1}" == "'" && "${s: -1}" == "'" ]]; then
    s="${s:1:${#s}-2}"
  fi
  printf "%s" "$s"
}

strip_inline_comment_unquoted() {
  # If value is unquoted, strip trailing inline comment (# ...)
  # If quoted, keep full content including #.
  local s="$1"
  s="$(trim "$s")"
  if [[ -z "$s" ]]; then
    printf "%s" "$s"
    return
  fi

  local first="${s:0:1}"
  if [[ "$first" == "\"" || "$first" == "'" ]]; then
    printf "%s" "$s"
    return
  fi

  # Unquoted: remove inline comment
  s="$(echo "$s" | sed -E 's/[[:space:]]+#.*$//')"
  s="$(trim "$s")"
  printf "%s" "$s"
}

read_env_value() {
  # Supports:
  # KEY=...
  # KEY = ...
  # export KEY=...
  # KEY="..."
  # KEY='...'
  # KEY=... # inline comment
  local file="$1"
  local key="$2"

  [[ -f "$file" ]] || return 1

  local line raw value
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$file" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1

  raw="${line#*=}"
  raw="$(trim "$raw")"

  # Strip inline comment only when unquoted
  raw="$(strip_inline_comment_unquoted "$raw")"

  value="$(strip_quotes "$raw")"
  printf "%s" "$value"
}

normalize_db_url() {
  local db_url="$1"
  db_url="${db_url/postgresql+asyncpg:\/\//postgresql://}"
  db_url="${db_url/postgres+asyncpg:\/\//postgresql://}"
  db_url="${db_url/postgres:\/\//postgresql://}"
  printf "%s" "$db_url"
}

redis_get_config_value_raw() {
  local redis_url="$1"
  local key="$2"
  redis-cli -u "$redis_url" --raw CONFIG GET "$key" | tail -n 1 | tr -d '\r'
}

wait_for_bgsave_complete() {
  # Fallback logic:
  # 1) read LASTSAVE(before)
  # 2) try BGSAVE
  # 3) if "Background save already in progress", keep waiting
  # 4) wait until rdb_bgsave_in_progress=0
  # 5) if this script started BGSAVE, also require LASTSAVE changed
  # 6) timeout -> fail
  local redis_url="$1"
  local timeout_sec="${2:-120}"

  local before lastsave inprog waited bgsave_out started_by_us must_require_lastsave_change
  before="$(redis-cli -u "$redis_url" LASTSAVE | tr -d '\r\n')"

  set +e
  bgsave_out="$(redis-cli -u "$redis_url" BGSAVE 2>&1)"
  bgsave_rc=$?
  set -e

  started_by_us=0
  must_require_lastsave_change=0

  if [[ $bgsave_rc -eq 0 ]]; then
    started_by_us=1
    must_require_lastsave_change=1
  else
    if echo "$bgsave_out" | grep -qi "Background save already in progress"; then
      started_by_us=0
      must_require_lastsave_change=0
      warn "Redis reported: Background save already in progress; will wait for completion."
    else
      err "Redis BGSAVE failed: $bgsave_out"
      exit 1
    fi
  fi

  waited=0
  while true; do
    inprog="$(redis-cli -u "$redis_url" INFO persistence | grep -E '^rdb_bgsave_in_progress:' | cut -d: -f2 | tr -d '\r\n' || true)"
    lastsave="$(redis-cli -u "$redis_url" LASTSAVE | tr -d '\r\n' || true)"

    if [[ "$inprog" == "0" ]]; then
      if [[ "$must_require_lastsave_change" -eq 1 ]]; then
        if [[ "$lastsave" != "$before" ]]; then
          break
        fi
      else
        # Existing background save case: in_progress ended is enough
        break
      fi
    fi

    sleep 1
    waited=$((waited + 1))
    if [[ $waited -ge $timeout_sec ]]; then
      err "Timeout waiting for Redis BGSAVE completion."
      exit 1
    fi
  done
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --include-env)
      INCLUDE_ENV=1
      shift
      ;;
    --name)
      ARCHIVE_NAME="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

require_cmd tar
require_cmd pg_dump
require_cmd redis-cli
require_cmd sha256sum
require_cmd hostname
require_cmd date
require_cmd mktemp
require_cmd python3
require_cmd find
require_cmd sort
require_cmd xargs

BACKEND_ENV="${PROJECT_DIR}/backend/.env"
if [[ ! -f "$BACKEND_ENV" ]]; then
  err "Missing backend env file: $BACKEND_ENV"
  exit 1
fi

DATABASE_URL="$(read_env_value "$BACKEND_ENV" "DATABASE_URL" || true)"
REDIS_URL="$(read_env_value "$BACKEND_ENV" "REDIS_URL" || true)"

if [[ -z "$DATABASE_URL" ]]; then
  err "DATABASE_URL not found in $BACKEND_ENV"
  exit 1
fi
if [[ -z "$REDIS_URL" ]]; then
  err "REDIS_URL not found in $BACKEND_ENV"
  exit 1
fi

DB_URL_PG="$(normalize_db_url "$DATABASE_URL")"

timestamp="$(date +%Y%m%d-%H%M%S)"
if [[ -z "$ARCHIVE_NAME" ]]; then
  ARCHIVE_NAME="multi-agents-backup-${timestamp}.tar.gz"
fi

mkdir -p "$OUTPUT_DIR"
chmod 700 "$OUTPUT_DIR"

WORK_PARENT="$(mktemp -d /tmp/multi-agents-backup.XXXXXX)"
trap 'rm -rf "$WORK_PARENT"' EXIT

TOP_DIR_NAME="multi-agents-backup-${timestamp}"
WORK_DIR="${WORK_PARENT}/${TOP_DIR_NAME}"

mkdir -p "$WORK_DIR/config/nginx/sites-enabled"
mkdir -p "$WORK_DIR/config/nginx/conf.d"
mkdir -p "$WORK_DIR/config/systemd"

log "Project dir: $PROJECT_DIR"
log "Output dir: $OUTPUT_DIR"
log "Archive: $ARCHIVE_NAME"

# 1) PostgreSQL dump
log "Dumping PostgreSQL..."
PG_DUMP_FILE="$WORK_DIR/postgres.dump"
pg_dump "$DB_URL_PG" -Fc -f "$PG_DUMP_FILE"

# 2) Redis snapshot
log "Backing up Redis..."
REDIS_BACKUP_OK=0

# Preferred method: redis-cli --rdb
if redis-cli -u "$REDIS_URL" --rdb "$WORK_DIR/redis.rdb" >/dev/null 2>&1; then
  REDIS_BACKUP_OK=1
  log "Redis backup via redis-cli --rdb succeeded."
else
  warn "redis-cli --rdb failed, fallback to BGSAVE + copy dump.rdb."
fi

if [[ "$REDIS_BACKUP_OK" -ne 1 ]]; then
  wait_for_bgsave_complete "$REDIS_URL" 120

  redis_dir="$(redis_get_config_value_raw "$REDIS_URL" "dir")"
  redis_dbfilename="$(redis_get_config_value_raw "$REDIS_URL" "dbfilename")"

  if [[ -z "$redis_dir" || -z "$redis_dbfilename" ]]; then
    err "Failed to read Redis dir/dbfilename in fallback mode."
    exit 1
  fi

  redis_source_rdb="${redis_dir%/}/${redis_dbfilename}"
  if [[ ! -f "$redis_source_rdb" ]]; then
    err "Redis dump file not found: $redis_source_rdb"
    exit 1
  fi

  cp "$redis_source_rdb" "$WORK_DIR/redis.rdb"
  REDIS_BACKUP_OK=1
fi

if [[ ! -f "$WORK_DIR/redis.rdb" ]]; then
  err "Redis backup failed: redis.rdb not generated."
  exit 1
fi

# 3) Nginx configs
log "Backing up nginx configs..."
if [[ -f /etc/nginx/nginx.conf ]]; then
  cp /etc/nginx/nginx.conf "$WORK_DIR/config/nginx/nginx.conf"
else
  warn "/etc/nginx/nginx.conf not found"
fi

if [[ -d /etc/nginx/sites-enabled ]]; then
  cp -a /etc/nginx/sites-enabled/. "$WORK_DIR/config/nginx/sites-enabled/" || true
else
  warn "/etc/nginx/sites-enabled not found"
fi

if [[ -d /etc/nginx/conf.d ]]; then
  cp -a /etc/nginx/conf.d/. "$WORK_DIR/config/nginx/conf.d/" || true
else
  warn "/etc/nginx/conf.d not found"
fi

# 4) systemd backend service
log "Backing up systemd service..."
if [[ -f /etc/systemd/system/multi-agents-backend.service ]]; then
  cp /etc/systemd/system/multi-agents-backend.service "$WORK_DIR/config/systemd/multi-agents-backend.service"
else
  warn "/etc/systemd/system/multi-agents-backend.service not found"
fi

# 5) optional env
if [[ "$INCLUDE_ENV" -eq 1 ]]; then
  warn "Including backend/.env in backup package. It may contain sensitive secrets (API keys/passwords)."
  cp "$BACKEND_ENV" "$WORK_DIR/config/backend.env"
fi

# 6) manifest.json (JSON-safe with python3)
git_commit="unknown"
if command -v git >/dev/null 2>&1 && [[ -d "${PROJECT_DIR}/.git" ]]; then
  git_commit="$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
fi

contains_nginx_config=False
contains_systemd_config=False
[[ -f "$WORK_DIR/config/nginx/nginx.conf" ]] && contains_nginx_config=True
[[ -f "$WORK_DIR/config/systemd/multi-agents-backend.service" ]] && contains_systemd_config=True

python3 - <<PY > "${WORK_DIR}/manifest.json"
import json, datetime, socket
manifest = {
  "app": "multi-agents",
  "created_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
  "hostname": socket.gethostname(),
  "project_dir": ${PROJECT_DIR@Q},
  "git_commit": ${git_commit@Q},
  "include_env": bool(${INCLUDE_ENV}),
  "contains_postgres": True,
  "contains_redis": True,
  "contains_nginx_config": ${contains_nginx_config},
  "contains_systemd_config": ${contains_systemd_config},
  "archive_name": ${ARCHIVE_NAME@Q},
}
print(json.dumps(manifest, ensure_ascii=False, indent=2))
PY

# 7) checksums inside package (cover all files except checksums.sha256 itself)
(
  cd "$WORK_DIR"
  find . -type f ! -name checksums.sha256 -print0 \
    | sort -z \
    | xargs -0 sha256sum > checksums.sha256
)

# 8) archive with top-level directory
ARCHIVE_PATH="${OUTPUT_DIR}/${ARCHIVE_NAME}"
(
  cd "$WORK_PARENT"
  tar -czf "$ARCHIVE_PATH" "$TOP_DIR_NAME"
)

chmod 600 "$ARCHIVE_PATH"

# 9) archive-level checksum
sha256sum "$ARCHIVE_PATH" > "${ARCHIVE_PATH}.sha256"
chmod 600 "${ARCHIVE_PATH}.sha256"

log "Backup completed."
echo "Archive: ${ARCHIVE_PATH}"
echo "Checksum: ${ARCHIVE_PATH}.sha256"

if [[ "$INCLUDE_ENV" -ne 1 ]]; then
  warn "backend/.env was NOT included. Keep a secure separate backup of backend/.env for full restore."
fi
