#!/usr/bin/env bash
set -euo pipefail

# multi-agents ECS local restore script
# Restore PostgreSQL + Redis + optional env/config from backup package

PROJECT_DIR="/opt/multi-agents"
ARCHIVE_PATH=""
RESTORE_ENV=0
RESTORE_CONFIG=0
DB_URL_OVERRIDE=""
REDIS_URL_OVERRIDE=""
BACKEND_SERVICE="multi-agents-backend"
NGINX_SERVICE="nginx"

SCRIPT_NAME="$(basename "$0")"

usage() {
  cat <<EOF
Usage:
  ${SCRIPT_NAME} --archive PATH [options]

Required:
  --archive PATH               Backup archive path (.tar.gz)

Options:
  --project-dir PATH           Project root directory (default: /opt/multi-agents)
  --restore-env                Restore backend env from config/backend.env (if exists in package)
  --restore-config             Restore nginx + systemd config from package
  --db-url URL                 Override DB URL (else read from backend/.env)
  --redis-url URL              Override Redis URL (else read from backend/.env)
  --backend-service NAME       Backend systemd service name (default: multi-agents-backend)
  --nginx-service NAME         Nginx systemd service name (default: nginx)
  -h, --help                   Show this help

Examples:
  ${SCRIPT_NAME} --archive /opt/backups/multi-agents/multi-agents-backup-20260507-120000.tar.gz
  ${SCRIPT_NAME} --archive /opt/backups/multi-agents/backup.tar.gz --restore-env --restore-config
EOF
}

log() {
  echo "[restore] $*"
}

warn() {
  echo "[restore][WARN] $*" >&2
}

err() {
  echo "[restore][ERROR] $*" >&2
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
  s="$(echo "$s" | sed -E 's/[[:space:]]+#.*$//')"
  s="$(trim "$s")"
  printf "%s" "$s"
}

read_env_value() {
  local file="$1"
  local key="$2"

  [[ -f "$file" ]] || return 1

  local line raw value
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$file" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 1

  raw="${line#*=}"
  raw="$(trim "$raw")"
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

detect_redis_service_name() {
  if systemctl list-unit-files | grep -q '^redis-server\.service'; then
    echo "redis-server"
    return
  fi
  if systemctl list-unit-files | grep -q '^redis\.service'; then
    echo "redis"
    return
  fi
  echo ""
}

redis_get_config_value_raw() {
  local redis_url="$1"
  local key="$2"
  redis-cli -u "$redis_url" --raw CONFIG GET "$key" | tail -n 1 | tr -d '\r'
}

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive)
      ARCHIVE_PATH="${2:-}"
      shift 2
      ;;
    --project-dir)
      PROJECT_DIR="${2:-}"
      shift 2
      ;;
    --restore-env)
      RESTORE_ENV=1
      shift
      ;;
    --restore-config)
      RESTORE_CONFIG=1
      shift
      ;;
    --db-url)
      DB_URL_OVERRIDE="${2:-}"
      shift 2
      ;;
    --redis-url)
      REDIS_URL_OVERRIDE="${2:-}"
      shift 2
      ;;
    --backend-service)
      BACKEND_SERVICE="${2:-}"
      shift 2
      ;;
    --nginx-service)
      NGINX_SERVICE="${2:-}"
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

if [[ -z "$ARCHIVE_PATH" ]]; then
  err "--archive is required"
  usage
  exit 1
fi

if [[ ! -f "$ARCHIVE_PATH" ]]; then
  err "Archive not found: $ARCHIVE_PATH"
  exit 1
fi

require_cmd tar
require_cmd pg_restore
require_cmd redis-cli
require_cmd curl
require_cmd sha256sum
require_cmd systemctl
require_cmd date
require_cmd mktemp

BACKEND_ENV="${PROJECT_DIR}/backend/.env"

echo "============================================================"
echo "DANGER: This restore operation will:"
echo "1) OVERWRITE PostgreSQL data (target DB)"
echo "2) OVERWRITE Redis dump.rdb"
echo "3) STOP and RESTART backend/redis/nginx services"
echo "Archive: $ARCHIVE_PATH"
echo "============================================================"
read -r -p "Type RESTORE to continue: " confirm
if [[ "$confirm" != "RESTORE" ]]; then
  err "Confirmation failed. Abort."
  exit 1
fi

WORK_DIR="$(mktemp -d /tmp/multi-agents-restore.XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

log "Extracting archive..."
tar -xzf "$ARCHIVE_PATH" -C "$WORK_DIR"

# Detect top-level backup directory
TOP_DIR="$(find "$WORK_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1 || true)"
if [[ -z "$TOP_DIR" ]]; then
  err "Cannot find top-level directory in archive."
  exit 1
fi

# Verify checksums inside package if exists
if [[ -f "$TOP_DIR/checksums.sha256" ]]; then
  log "Verifying package checksums..."
  (
    cd "$TOP_DIR"
    sha256sum -c checksums.sha256
  )
fi

# Resolve DB/Redis URLs
DATABASE_URL="${DB_URL_OVERRIDE}"
REDIS_URL="${REDIS_URL_OVERRIDE}"

if [[ -z "$DATABASE_URL" ]]; then
  if [[ -f "$BACKEND_ENV" ]]; then
    DATABASE_URL="$(read_env_value "$BACKEND_ENV" "DATABASE_URL" || true)"
  fi
fi
if [[ -z "$REDIS_URL" ]]; then
  if [[ -f "$BACKEND_ENV" ]]; then
    REDIS_URL="$(read_env_value "$BACKEND_ENV" "REDIS_URL" || true)"
  fi
fi

if [[ -z "$DATABASE_URL" ]]; then
  err "DATABASE_URL not found. Provide --db-url or ensure ${BACKEND_ENV} exists."
  exit 1
fi
if [[ -z "$REDIS_URL" ]]; then
  err "REDIS_URL not found. Provide --redis-url or ensure ${BACKEND_ENV} exists."
  exit 1
fi

DB_URL_PG="$(normalize_db_url "$DATABASE_URL")"

# Stop backend first
log "Stopping backend service: ${BACKEND_SERVICE}"
systemctl stop "$BACKEND_SERVICE" || true

# Restore PostgreSQL
if [[ ! -f "$TOP_DIR/postgres.dump" ]]; then
  err "postgres.dump not found in archive"
  exit 1
fi
log "Restoring PostgreSQL from postgres.dump ..."
pg_restore --clean --if-exists --no-owner --no-acl -d "$DB_URL_PG" "$TOP_DIR/postgres.dump"

# Prepare Redis restore paths BEFORE stopping Redis
if [[ ! -f "$TOP_DIR/redis.rdb" ]]; then
  err "redis.rdb not found in archive"
  exit 1
fi

appendonly="$(redis_get_config_value_raw "$REDIS_URL" "appendonly")"
if [[ "${appendonly}" == "yes" ]]; then
  err "Redis appendonly=yes detected. Overwriting dump.rdb may not take effect."
  err "Please handle AOF manually (or disable AOF) before restore."
  exit 1
fi

redis_dir="$(redis_get_config_value_raw "$REDIS_URL" "dir")"
redis_dbfilename="$(redis_get_config_value_raw "$REDIS_URL" "dbfilename")"

if [[ -z "$redis_dir" || -z "$redis_dbfilename" ]]; then
  err "Failed to read Redis dir/dbfilename via redis-cli."
  exit 1
fi

target_rdb="${redis_dir%/}/${redis_dbfilename}"

REDIS_SERVICE="$(detect_redis_service_name)"
if [[ -z "$REDIS_SERVICE" ]]; then
  warn "Could not detect redis systemd service name automatically."
  warn "Will attempt restore while Redis is running (may fail)."
else
  log "Stopping Redis service: ${REDIS_SERVICE}"
  systemctl stop "$REDIS_SERVICE" || true
fi

log "Restoring Redis RDB to: ${target_rdb}"
cp "$TOP_DIR/redis.rdb" "$target_rdb"

if id redis >/dev/null 2>&1; then
  chown redis:redis "$target_rdb" || true
fi
chmod 600 "$target_rdb" || true

if [[ -n "$REDIS_SERVICE" ]]; then
  log "Starting Redis service: ${REDIS_SERVICE}"
  systemctl start "$REDIS_SERVICE"
fi

# Optional restore env
if [[ "$RESTORE_ENV" -eq 1 ]]; then
  if [[ -f "$TOP_DIR/config/backend.env" ]]; then
    ts="$(date +%Y%m%d-%H%M%S)"
    if [[ -f "$BACKEND_ENV" ]]; then
      cp "$BACKEND_ENV" "${BACKEND_ENV}.before-restore-${ts}"
      chmod 600 "${BACKEND_ENV}.before-restore-${ts}" || true
      log "Current backend/.env backup: ${BACKEND_ENV}.before-restore-${ts}"
    fi
    cp "$TOP_DIR/config/backend.env" "$BACKEND_ENV"
    chmod 600 "$BACKEND_ENV" || true
    log "Restored backend env to: $BACKEND_ENV"
  else
    warn "--restore-env set, but config/backend.env not found in package"
  fi
else
  log "Skip env restore (default). Use --restore-env to enable."
fi

# Optional restore configs
if [[ "$RESTORE_CONFIG" -eq 1 ]]; then
  log "Restoring nginx and systemd configs with pre-backup..."

  ts="$(date +%Y%m%d-%H%M%S)"

  # Backup current nginx.conf
  if [[ -f /etc/nginx/nginx.conf ]]; then
    cp /etc/nginx/nginx.conf "/etc/nginx/nginx.conf.before-restore-${ts}"
  fi

  # Backup current backend service file
  if [[ -f "/etc/systemd/system/${BACKEND_SERVICE}.service" ]]; then
    cp "/etc/systemd/system/${BACKEND_SERVICE}.service" "/etc/systemd/system/${BACKEND_SERVICE}.service.before-restore-${ts}"
  fi

  # Restore files
  if [[ -f "$TOP_DIR/config/nginx/nginx.conf" ]]; then
    cp "$TOP_DIR/config/nginx/nginx.conf" /etc/nginx/nginx.conf
  fi

  if [[ -d "$TOP_DIR/config/nginx/sites-enabled" ]]; then
    mkdir -p /etc/nginx/sites-enabled
    cp -a "$TOP_DIR/config/nginx/sites-enabled/." /etc/nginx/sites-enabled/
  fi

  if [[ -d "$TOP_DIR/config/nginx/conf.d" ]]; then
    mkdir -p /etc/nginx/conf.d
    cp -a "$TOP_DIR/config/nginx/conf.d/." /etc/nginx/conf.d/
  fi

  if [[ -f "$TOP_DIR/config/systemd/multi-agents-backend.service" ]]; then
    cp "$TOP_DIR/config/systemd/multi-agents-backend.service" "/etc/systemd/system/${BACKEND_SERVICE}.service"
  fi

  systemctl daemon-reload
else
  log "Skip nginx/systemd config restore (default). Use --restore-config to enable."
fi

# Restart backend and nginx
log "Starting backend service: ${BACKEND_SERVICE}"
systemctl start "$BACKEND_SERVICE"

if systemctl list-unit-files | grep -q "^${NGINX_SERVICE}\.service"; then
  log "Reloading nginx service: ${NGINX_SERVICE}"
  systemctl reload "$NGINX_SERVICE" || systemctl restart "$NGINX_SERVICE"
else
  warn "Nginx service '${NGINX_SERVICE}' not found, skip nginx reload."
fi

# Health checks
log "Running health checks..."
backend_status="$(systemctl is-active "$BACKEND_SERVICE" || true)"
echo "backend_service_status=${backend_status}"

redis_ping="$(redis-cli -u "$REDIS_URL" PING | tr -d '\r\n' || true)"
echo "redis_ping=${redis_ping}"

openapi_status="$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/openapi.json || true)"
echo "openapi_http_status=${openapi_status}"

if [[ "$backend_status" != "active" ]]; then
  err "Backend service is not active after restore."
  exit 1
fi
if [[ "$redis_ping" != "PONG" ]]; then
  err "Redis ping failed after restore."
  exit 1
fi
if [[ "$openapi_status" != "200" ]]; then
  err "OpenAPI health check failed (http ${openapi_status})."
  exit 1
fi

log "Restore completed successfully."
