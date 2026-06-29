#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
CONFIG_PATH="${AUTOBOT_RESEARCH_CONFIG:-${REPO_DIR}/config/research_data_collection.yaml}"
RUN_ID="${AUTOBOT_RESEARCH_RUN_ID:-daily_$(date -u +%Y_%m_%dT%H_%M_%SZ)}"
LOCK_PATH="${AUTOBOT_RESEARCH_LOCK_PATH:-/run/lock/autobot-research-data.lock}"

DATA_DIR="${REPO_DIR}/data/research/daily"
REPORT_DIR="${REPO_DIR}/reports/research/daily_data_collection"
HIGH_CONVICTION_REPORT_DIR="${REPO_DIR}/reports/research/high_conviction_walk_forward"
STRATEGY_ORCHESTRATOR_REPORT_DIR="${REPO_DIR}/reports/research/strategy_orchestrator"
STRATEGY_EDGE_REPORT_DIR="${REPO_DIR}/reports/research/strategy_edge"

exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  echo "AUTOBOT research collection is already running; skipping ${RUN_ID}."
  exit 0
fi

if [[ ! -r "${CONFIG_PATH}" ]]; then
  echo "Research collection config is not readable: ${CONFIG_PATH}" >&2
  exit 1
fi

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "Research image is unavailable: ${IMAGE}" >&2
  exit 1
fi

# The image runs as appuser (uid/gid 999). Only research output directories are
# mounted, so the collector cannot read the runtime database, logs, or .env.
install -d -o 999 -g 999 -m 0775 "${DATA_DIR}" "${REPORT_DIR}" "${HIGH_CONVICTION_REPORT_DIR}" "${STRATEGY_ORCHESTRATOR_REPORT_DIR}" "${STRATEGY_EDGE_REPORT_DIR}"
# install -d preserves ownership for pre-existing directories. Restore the
# appuser-owned output boundary so a prior root-created report cannot make a
# subsequent isolated daily run fail while writing its research artifacts.
chown 999:999 "${DATA_DIR}" "${REPORT_DIR}" "${HIGH_CONVICTION_REPORT_DIR}" "${STRATEGY_ORCHESTRATOR_REPORT_DIR}" "${STRATEGY_EDGE_REPORT_DIR}"
chmod 0775 "${DATA_DIR}" "${REPORT_DIR}" "${HIGH_CONVICTION_REPORT_DIR}" "${STRATEGY_ORCHESTRATOR_REPORT_DIR}" "${STRATEGY_EDGE_REPORT_DIR}"

exec docker run --rm \
  --name "autobot-research-${RUN_ID}" \
  --label "autobot.component=research-data-collection" \
  --network bridge \
  --no-healthcheck \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --memory 768m \
  --cpus 0.50 \
  --env PYTHONPATH=/app/src \
  --env PYTHONUNBUFFERED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env HOME=/tmp \
  --env TZ=Europe/Paris \
  --volume "${CONFIG_PATH}:/app/config/research_data_collection.yaml:ro" \
  --volume "${DATA_DIR}:/app/data/research/daily" \
  --volume "${REPORT_DIR}:/app/reports/research/daily_data_collection" \
  --volume "${HIGH_CONVICTION_REPORT_DIR}:/app/reports/research/high_conviction_walk_forward" \
  --volume "${STRATEGY_ORCHESTRATOR_REPORT_DIR}:/app/reports/research/strategy_orchestrator" \
  --volume "${STRATEGY_EDGE_REPORT_DIR}:/app/reports/research/strategy_edge" \
  "${IMAGE}" \
  python -m autobot.v2.cli collect-research-daily \
    --config /app/config/research_data_collection.yaml \
    --run-id "${RUN_ID}"
