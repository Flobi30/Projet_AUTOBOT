#!/usr/bin/env bash
set -euo pipefail

# This job is intentionally disabled until an operator has approved retention
# and off-VPS encryption. It only creates a local, integrity-checked snapshot;
# it never starts AUTOBOT, touches order paths or mounts secrets.
REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
BACKUP_ENABLED="${AUTOBOT_SQLITE_BACKUP_ENABLED:-false}"
EXTERNAL_POLICY_APPROVED="${AUTOBOT_SQLITE_BACKUP_EXTERNAL_POLICY_APPROVED:-false}"
RUN_ID="${AUTOBOT_SQLITE_BACKUP_RUN_ID:-sqlite_$(date -u +%Y_%m_%dT%H_%M_%SZ)}"
LOCK_PATH="${AUTOBOT_SQLITE_BACKUP_LOCK_PATH:-/run/lock/autobot-sqlite-backup.lock}"
BACKUP_DIR="${AUTOBOT_SQLITE_BACKUP_DIR:-${REPO_DIR}/backups/sqlite}"

if [[ "${BACKUP_ENABLED}" != "true" ]]; then
  echo "AUTOBOT SQLite backup is disabled pending explicit storage approval."
  exit 0
fi
if [[ "${EXTERNAL_POLICY_APPROVED}" != "true" ]]; then
  echo "AUTOBOT SQLite backup requires approved retention and off-VPS encryption policy." >&2
  exit 1
fi

exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  echo "AUTOBOT SQLite backup is already running; skipping ${RUN_ID}."
  exit 0
fi

if [[ ! -r "${REPO_DIR}/data/autobot_state.db" ]]; then
  echo "AUTOBOT runtime SQLite database is unavailable." >&2
  exit 1
fi
if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "AUTOBOT backup image is unavailable: ${IMAGE}" >&2
  exit 1
fi

# appuser is uid/gid 999 in the immutable image. The source is mounted read
# only; only a dedicated local backup directory is writable.
install -d -o 999 -g 999 -m 0700 "${BACKUP_DIR}"
chown 999:999 "${BACKUP_DIR}"
chmod 0700 "${BACKUP_DIR}"

exec docker run --rm \
  --name "autobot-sqlite-backup-${RUN_ID}" \
  --label "autobot.component=sqlite-backup" \
  --network none \
  --no-healthcheck \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --memory 512m \
  --cpus 0.25 \
  --env PYTHONPATH=/app/src \
  --env PYTHONUNBUFFERED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env HOME=/tmp \
  --env TZ=UTC \
  --volume "${REPO_DIR}/data:/app/data:ro" \
  --volume "${BACKUP_DIR}:/app/backups" \
  "${IMAGE}" \
  python -m autobot.v2.cli sqlite-backup \
    --source /app/data/autobot_state.db \
    --backup-path "/app/backups/${RUN_ID}.sqlite3" \
    --manifest-path "/app/backups/${RUN_ID}.json"
