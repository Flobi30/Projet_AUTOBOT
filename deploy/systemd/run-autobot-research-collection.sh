#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
CONFIG_PATH="${AUTOBOT_RESEARCH_CONFIG:-${REPO_DIR}/config/research_data_collection.yaml}"
RUN_ID="${AUTOBOT_RESEARCH_RUN_ID:-daily_$(date -u +%Y_%m_%dT%H_%M_%SZ)}"
LOCK_PATH="${AUTOBOT_RESEARCH_LOCK_PATH:-/run/lock/autobot-research-data.lock}"
MEMORY_LIMIT="${AUTOBOT_RESEARCH_MEMORY_LIMIT:-1536m}"
CPU_LIMIT="${AUTOBOT_RESEARCH_CPU_LIMIT:-0.50}"

DATA_DIR="${REPO_DIR}/data/research/daily"
CANONICAL_OHLCV_DIR="${REPO_DIR}/data/research/canonical/ohlcv"
CANONICAL_FEATURES_DIR="${REPO_DIR}/data/research/canonical/features"
CANONICAL_MANIFEST_DIR="${REPO_DIR}/data/research/manifests"
CANONICAL_QUARANTINE_DIR="${REPO_DIR}/data/research/quarantine"
HIGH_CONVICTION_SHADOW_SYNC_DIR="${REPO_DIR}/data/research/high_conviction_shadow_sync"
REPORT_DIR="${REPO_DIR}/reports/research/daily_data_collection"
HIGH_CONVICTION_REPORT_DIR="${REPO_DIR}/reports/research/high_conviction_walk_forward"
STRATEGY_ORCHESTRATOR_REPORT_DIR="${REPO_DIR}/reports/research/strategy_orchestrator"
STRATEGY_EDGE_REPORT_DIR="${REPO_DIR}/reports/research/strategy_edge"
SHADOW_OBSERVATION_REPORT_DIR="${REPO_DIR}/reports/paper/shadow_observations"

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

# The image runs as appuser (uid/gid 999). Its only writable data mount is
# data/research, so this public-data job cannot write the runtime state DB or
# any paper/live ledger. Canonical artifacts remain inside that boundary.
install -d -o 999 -g 999 -m 0775 "${DATA_DIR}" "${CANONICAL_OHLCV_DIR}" "${CANONICAL_FEATURES_DIR}" "${CANONICAL_MANIFEST_DIR}" "${CANONICAL_QUARANTINE_DIR}" "${HIGH_CONVICTION_SHADOW_SYNC_DIR}" "${REPORT_DIR}" "${HIGH_CONVICTION_REPORT_DIR}" "${STRATEGY_ORCHESTRATOR_REPORT_DIR}" "${STRATEGY_EDGE_REPORT_DIR}" "${SHADOW_OBSERVATION_REPORT_DIR}"
# install -d preserves ownership for pre-existing directories. Restore the
# appuser-owned output boundary so a prior root-created report cannot make a
# subsequent isolated daily run fail while writing its research artifacts.
chown 999:999 "${DATA_DIR}" "${CANONICAL_OHLCV_DIR}" "${CANONICAL_FEATURES_DIR}" "${CANONICAL_MANIFEST_DIR}" "${CANONICAL_QUARANTINE_DIR}" "${HIGH_CONVICTION_SHADOW_SYNC_DIR}" "${REPORT_DIR}" "${HIGH_CONVICTION_REPORT_DIR}" "${STRATEGY_ORCHESTRATOR_REPORT_DIR}" "${STRATEGY_EDGE_REPORT_DIR}" "${SHADOW_OBSERVATION_REPORT_DIR}"
chmod 0775 "${DATA_DIR}" "${CANONICAL_OHLCV_DIR}" "${CANONICAL_FEATURES_DIR}" "${CANONICAL_MANIFEST_DIR}" "${CANONICAL_QUARANTINE_DIR}" "${HIGH_CONVICTION_SHADOW_SYNC_DIR}" "${REPORT_DIR}" "${HIGH_CONVICTION_REPORT_DIR}" "${STRATEGY_ORCHESTRATOR_REPORT_DIR}" "${STRATEGY_EDGE_REPORT_DIR}" "${SHADOW_OBSERVATION_REPORT_DIR}"

docker run --rm \
  --name "autobot-research-${RUN_ID}" \
  --label "autobot.component=research-data-collection" \
  --network bridge \
  --no-healthcheck \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --memory "${MEMORY_LIMIT}" \
  --cpus "${CPU_LIMIT}" \
  --env PYTHONPATH=/app/src \
  --env PYTHONUNBUFFERED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env HOME=/tmp \
  --env TZ=Europe/Paris \
  --volume "${CONFIG_PATH}:/app/config/research_data_collection.yaml:ro" \
  --volume "${REPO_DIR}/data/research:/app/data/research" \
  --volume "${REPORT_DIR}:/app/reports/research/daily_data_collection" \
  --volume "${HIGH_CONVICTION_REPORT_DIR}:/app/reports/research/high_conviction_walk_forward" \
  --volume "${STRATEGY_ORCHESTRATOR_REPORT_DIR}:/app/reports/research/strategy_orchestrator" \
  --volume "${STRATEGY_EDGE_REPORT_DIR}:/app/reports/research/strategy_edge" \
  --volume "${SHADOW_OBSERVATION_REPORT_DIR}:/app/reports/paper/shadow_observations" \
  "${IMAGE}" \
  python -m autobot.v2.cli collect-research-daily \
    --config /app/config/research_data_collection.yaml \
    --run-id "${RUN_ID}"

# The collector only produces data. Run a separate read-only capability scan
# afterwards so the next research scheduler cycle has an auditable explanation
# of which alpha families remain blocked by data, without launching a strategy.
docker run --rm \
  --name "autobot-research-capability-${RUN_ID}" \
  --label "autobot.component=research-data-capability" \
  --network none \
  --no-healthcheck \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --memory "${MEMORY_LIMIT}" \
  --cpus "${CPU_LIMIT}" \
  --env PYTHONPATH=/app/src \
  --env PYTHONUNBUFFERED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env HOME=/tmp \
  --env TZ=Europe/Paris \
  --volume "${REPO_DIR}/data:/app/data:ro" \
  --volume "${REPORT_DIR}:/app/reports/research/daily_data_collection" \
  "${IMAGE}" \
  python -m autobot.v2.cli data-capability-scan \
    --run-id "${RUN_ID}_capability" \
    --state-db data/autobot_state.db \
    --data-roots data/research \
    --memory-path data/research/alpha_research_memory.sqlite3 \
    --output-dir reports/research/daily_data_collection

# Rank the next bounded research hypothesis after data collection.  This is a
# read-only planning step: it cannot run a strategy, mutate the research
# memory, or reach any execution surface.  The scheduler's recommendations
# remain reports for human review and the existing research gates.
docker run --rm \
  --name "autobot-research-scheduler-${RUN_ID}" \
  --label "autobot.component=research-hypothesis-scheduler" \
  --network none \
  --no-healthcheck \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --memory "${MEMORY_LIMIT}" \
  --cpus "${CPU_LIMIT}" \
  --env PYTHONPATH=/app/src \
  --env PYTHONUNBUFFERED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env HOME=/tmp \
  --env TZ=Europe/Paris \
  --volume "${REPO_DIR}/data/research:/app/data/research:ro" \
  --volume "${REPORT_DIR}:/app/reports/research/daily_data_collection" \
  "${IMAGE}" \
  python -m autobot.v2.cli alpha-hypothesis-scheduler \
    --run-id "${RUN_ID}_scheduler" \
    --data-paths data/research/canonical/ohlcv \
    --memory-path data/research/alpha_research_memory.sqlite3 \
    --output-dir reports/research/daily_data_collection \
    --no-memory-backfill
