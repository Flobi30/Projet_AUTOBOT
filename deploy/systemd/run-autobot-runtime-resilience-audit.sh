#!/usr/bin/env bash
set -euo pipefail

# This operational monitor is deliberately separate from the AUTOBOT runtime.
# It observes localhost health and a read-only SQLite mount only. It cannot
# access networked exchanges from its disposable container, use secrets, or
# invoke an order/paper path.
REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
AUDIT_ENABLED="${AUTOBOT_RUNTIME_RESILIENCE_AUDIT_ENABLED:-false}"
MAX_DATA_AGE_SECONDS="${AUTOBOT_RUNTIME_RESILIENCE_MAX_DATA_AGE_SECONDS:-300}"
MIN_FREE_DISK_BYTES="${AUTOBOT_RUNTIME_RESILIENCE_MIN_FREE_DISK_BYTES:-2147483648}"
HEALTH_WAIT_SECONDS="${AUTOBOT_RUNTIME_RESILIENCE_HEALTH_WAIT_SECONDS:-45}"
LOCK_PATH="${AUTOBOT_RUNTIME_RESILIENCE_AUDIT_LOCK_PATH:-/run/lock/autobot-runtime-resilience-audit.lock}"
REPORT_DIR="${AUTOBOT_RUNTIME_RESILIENCE_REPORT_DIR:-${REPO_DIR}/data/research/reports/runtime_resilience}"
REPORT_PATH="${REPORT_DIR}/latest.json"
TEMP_REPORT_PATH="${REPORT_DIR}/latest.json.tmp"

if [[ "${AUDIT_ENABLED}" != "true" ]]; then
  echo "AUTOBOT runtime resilience audit is disabled."
  exit 0
fi
if ! [[ "${HEALTH_WAIT_SECONDS}" =~ ^[0-9]+$ ]]; then
  echo "AUTOBOT runtime resilience health wait must be a non-negative integer." >&2
  exit 1
fi

exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  echo "AUTOBOT runtime resilience audit is already running; skipping."
  exit 0
fi

if [[ ! -r "${REPO_DIR}/data/autobot_state.db" ]]; then
  echo "AUTOBOT runtime SQLite database is unavailable." >&2
  exit 1
fi
if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "AUTOBOT resilience audit image is unavailable: ${IMAGE}" >&2
  exit 1
fi

websocket_status="unknown"
health_payload=""
health_deadline=$((SECONDS + HEALTH_WAIT_SECONDS))
while true; do
  health_payload="$(curl --fail --silent --max-time 5 http://127.0.0.1:8080/health || true)"
  if [[ "${health_payload}" =~ \"websocket\"[[:space:]]*:[[:space:]]*\"connected\" ]]; then
    websocket_status="connected"
    break
  fi
  if [[ "${health_payload}" =~ \"websocket\"[[:space:]]*:[[:space:]]*\"disconnected\" ]]; then
    websocket_status="disconnected"
  fi
  if (( SECONDS >= health_deadline )); then
    break
  fi
  sleep 3
done

umask 027
install -d -m 0750 "${REPORT_DIR}"

docker run --rm \
  --name "autobot-runtime-resilience-audit" \
  --label "autobot.component=runtime-resilience-audit" \
  --network none \
  --no-healthcheck \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --memory 256m \
  --cpus 0.25 \
  --env PYTHONPATH=/app/src \
  --env PYTHONUNBUFFERED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env HOME=/tmp \
  --env TZ=UTC \
  --volume "${REPO_DIR}/data:/app/data:ro" \
  "${IMAGE}" \
  python -m autobot.v2.cli runtime-resilience-audit \
    --state-db /app/data/autobot_state.db \
    --max-data-age-seconds "${MAX_DATA_AGE_SECONDS}" \
    --min-free-disk-bytes "${MIN_FREE_DISK_BYTES}" \
    --websocket-status "${websocket_status}" > "${TEMP_REPORT_PATH}"

mv -f "${TEMP_REPORT_PATH}" "${REPORT_PATH}"
cat "${REPORT_PATH}"

if grep -q '"status": "INCIDENTS_DETECTED"' "${REPORT_PATH}"; then
  echo "AUTOBOT runtime resilience incidents detected; see ${REPORT_PATH}." >&2
  exit 1
fi
if grep -q '"status": "PARTIAL_OBSERVABILITY"' "${REPORT_PATH}"; then
  echo "AUTOBOT runtime resilience evidence is incomplete; see ${REPORT_PATH}." >&2
  exit 2
fi
