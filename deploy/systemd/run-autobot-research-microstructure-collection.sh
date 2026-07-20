#!/usr/bin/env bash
set -euo pipefail

# Isolated public-data collector.  It intentionally does not mount .env, the
# runtime database, logs, or any execution surface.  Its output is canonical
# research evidence only, never a trading feed or an execution permission.
REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
RUN_ID="${AUTOBOT_MICROSTRUCTURE_RUN_ID:-microstructure_$(date -u +%Y_%m_%dT%H_%M_%SZ)}"
LOCK_PATH="${AUTOBOT_MICROSTRUCTURE_LOCK_PATH:-/run/lock/autobot-research-microstructure.lock}"
MEMORY_LIMIT="${AUTOBOT_MICROSTRUCTURE_MEMORY_LIMIT:-384m}"
CPU_LIMIT="${AUTOBOT_MICROSTRUCTURE_CPU_LIMIT:-0.25}"
DEPTH_COUNT="${AUTOBOT_MICROSTRUCTURE_DEPTH_COUNT:-10}"
SAMPLES="${AUTOBOT_MICROSTRUCTURE_SAMPLES:-1}"
MAX_RUNTIME_SECONDS="${AUTOBOT_MICROSTRUCTURE_MAX_RUNTIME_SECONDS:-300}"

# This is explicit rather than discovered from runtime environment variables:
# the research container receives no runtime configuration or credentials.
SYMBOLS="${AUTOBOT_MICROSTRUCTURE_SYMBOLS:-BTCZEUR,ETHZEUR,SOLEUR,LTCZEUR,XLMZEUR,XRPEUR,TRXEUR,ADAEUR,LINKEUR,DOTEUR,BCHEUR,ATOMEUR,AVAXEUR,AAVEEUR}"
RAW_DIR="${REPO_DIR}/data/research/forward/microstructure"
CANONICAL_DIR="${REPO_DIR}/data/research/canonical/microstructure"
MANIFEST_DIR="${REPO_DIR}/data/research/manifests"
REPORT_DIR="${REPO_DIR}/data/research/reports/microstructure"

exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  echo "AUTOBOT forward microstructure collection is already running; skipping ${RUN_ID}."
  exit 0
fi

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "AUTOBOT microstructure research image is unavailable: ${IMAGE}" >&2
  exit 1
fi

SOURCE_COMMIT="$(git -C "${REPO_DIR}" rev-parse HEAD)"
IMAGE_COMMIT="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "${IMAGE}" 2>/dev/null || true)"
if [[ ! "${IMAGE_COMMIT}" =~ ^[0-9a-f]{40}$ || "${IMAGE_COMMIT}" != "${SOURCE_COMMIT}" ]]; then
  echo "AUTOBOT forward microstructure collection blocked: image provenance mismatch (source=${SOURCE_COMMIT}, image=${IMAGE_COMMIT:-unverified})." >&2
  exit 1
fi

# uid/gid 999 is the non-root application user inside the immutable image.
# Only public research-data paths are writable; no runtime state is mounted.
install -d -o 999 -g 999 -m 0775 "${RAW_DIR}" "${CANONICAL_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"
chown 999:999 "${RAW_DIR}" "${CANONICAL_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"
chmod 0775 "${RAW_DIR}" "${CANONICAL_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"

exec docker run --rm \
  --name "autobot-research-microstructure-${RUN_ID}" \
  --label "autobot.component=research-microstructure-collection" \
  --label "autobot.job=research-microstructure" \
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
  --env TZ=UTC \
  --volume "${REPO_DIR}/data/research:/app/data/research" \
  "${IMAGE}" \
  python -m autobot.v2.cli collect-microstructure-forward \
    --run-id "${RUN_ID}" \
    --symbols "${SYMBOLS}" \
    --raw-output-dir /app/data/research/forward/microstructure \
    --canonical-output-dir /app/data/research/canonical/microstructure \
    --manifest-dir /app/data/research/manifests \
    --report-dir /app/data/research/reports/microstructure \
    --depth-count "${DEPTH_COUNT}" \
    --samples "${SAMPLES}" \
    --max-runtime-seconds "${MAX_RUNTIME_SECONDS}"
