#!/usr/bin/env bash
set -euo pipefail

# Create a private, ephemeral snapshot inside an isolated container and audit
# only that snapshot. The live research directory is mounted read-only; this
# job has no runtime-state mount, network, secrets, order path or paper/live
# authorization. A WAL source that cannot be read safely from the read-only
# mount fails closed instead of falling back to a live direct audit.
REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
AUDIT_ENABLED="${AUTOBOT_STRATEGY_ARTIFACT_READINESS_AUDIT_ENABLED:-false}"
LOCK_PATH="${AUTOBOT_STRATEGY_ARTIFACT_READINESS_AUDIT_LOCK_PATH:-/run/lock/autobot-strategy-artifact-readiness-audit.lock}"
REPORT_DIR="${AUTOBOT_STRATEGY_ARTIFACT_READINESS_AUDIT_REPORT_DIR:-${REPO_DIR}/data/research/reports/strategy_artifact_readiness}"
REPORT_PATH="${REPORT_DIR}/latest.json"
TEMP_REPORT_PATH="${REPORT_DIR}/latest.json.tmp"

if [[ "${AUDIT_ENABLED}" != "true" ]]; then
  echo "AUTOBOT strategy artifact readiness snapshot audit is disabled."
  exit 0
fi

exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  echo "AUTOBOT strategy artifact readiness snapshot audit is already running; skipping."
  exit 0
fi

if [[ ! -r "${REPO_DIR}/data/research/experiment_registry.sqlite3" ]]; then
  echo "AUTOBOT experiment registry is unavailable." >&2
  exit 1
fi
if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "AUTOBOT readiness-audit image is unavailable: ${IMAGE}" >&2
  exit 1
fi

SOURCE_COMMIT="$(git -C "${REPO_DIR}" rev-parse HEAD)"
IMAGE_COMMIT="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "${IMAGE}" 2>/dev/null || true)"
if [[ ! "${IMAGE_COMMIT}" =~ ^[0-9a-f]{40}$ || "${IMAGE_COMMIT}" != "${SOURCE_COMMIT}" ]]; then
  echo "AUTOBOT readiness snapshot audit blocked: image provenance mismatch (source=${SOURCE_COMMIT}, image=${IMAGE_COMMIT:-unverified})." >&2
  exit 1
fi

umask 027
install -d -m 0750 "${REPORT_DIR}"

docker run --rm \
  --name "autobot-strategy-artifact-readiness-audit" \
  --label "autobot.component=strategy-artifact-readiness-audit" \
  --network none \
  --no-healthcheck \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --memory 256m \
  --cpus 0.25 \
  --env PYTHONPATH=/app/src \
  --env PYTHONUNBUFFERED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env HOME=/tmp \
  --env TZ=UTC \
  --volume "${REPO_DIR}/data/research:/app/data/research:ro" \
  "${IMAGE}" \
  python -m autobot.v2.cli strategy-artifact-readiness-snapshot-audit \
    --registry-path /app/data/research/experiment_registry.sqlite3 \
    --artifact-registry-path /app/data/research/strategy_artifacts.sqlite3 > "${TEMP_REPORT_PATH}"

mv -f "${TEMP_REPORT_PATH}" "${REPORT_PATH}"
cat "${REPORT_PATH}"

if grep -q '"status": "SNAPSHOT_UNAVAILABLE"' "${REPORT_PATH}"; then
  echo "AUTOBOT readiness snapshot could not be verified; direct live-registry audit remains forbidden." >&2
  exit 2
fi
