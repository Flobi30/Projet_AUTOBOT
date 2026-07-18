#!/usr/bin/env bash
set -euo pipefail

# Materialize a bounded, forward-captured derivatives feature view.  This is
# research evidence only: it has no network, secrets, runtime-state mount, or
# execution surface.  It intentionally reports DATA_MISSING or
# WAITING_FOR_MORE_DATA until the public collectors have accumulated enough
# forward provenance; it never manufactures readiness from historical backfill.
REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
RUN_ID="${AUTOBOT_DERIVATIVES_FEATURE_RUN_ID:-derivatives_forward_features_$(date -u +%Y_%m_%dT%H_%M_%SZ)}"
LOCK_PATH="${AUTOBOT_DERIVATIVES_LOCK_PATH:-/run/lock/autobot-research-derivatives.lock}"
MEMORY_LIMIT="${AUTOBOT_DERIVATIVES_FEATURE_MEMORY_LIMIT:-768m}"
CPU_LIMIT="${AUTOBOT_DERIVATIVES_FEATURE_CPU_LIMIT:-0.25}"

MANIFEST_DIR="${REPO_DIR}/data/research/manifests"
FEATURE_DIR="${REPO_DIR}/data/research/canonical/derivatives_features"
REPORT_DIR="${REPO_DIR}/data/research/reports/derivatives_feature_snapshot"

exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  echo "AUTOBOT derivatives feature materialization is already blocked by a collector; skipping ${RUN_ID}."
  exit 0
fi

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "Research image is unavailable: ${IMAGE}" >&2
  exit 1
fi

SOURCE_COMMIT="$(git -C "${REPO_DIR}" rev-parse HEAD)"
IMAGE_COMMIT="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "${IMAGE}" 2>/dev/null || true)"
if [[ ! "${IMAGE_COMMIT}" =~ ^[0-9a-f]{40}$ || "${IMAGE_COMMIT}" != "${SOURCE_COMMIT}" ]]; then
  echo "AUTOBOT derivatives feature materialization blocked: image provenance mismatch (source=${SOURCE_COMMIT}, image=${IMAGE_COMMIT:-unverified})." >&2
  exit 1
fi

DERIVATIVES_MANIFEST="$({
  find "${MANIFEST_DIR}" -maxdepth 1 -type f -name '*_kraken_futures_derivatives.json' -printf '%T@ %f\n' \
    | sort -nr \
    | awk 'NR == 1 { print $2 }'
} || true)"
if [[ -z "${DERIVATIVES_MANIFEST}" || ! -r "${MANIFEST_DIR}/${DERIVATIVES_MANIFEST}" ]]; then
  echo "AUTOBOT derivatives feature materialization skipped: no collector manifest is available."
  exit 0
fi

# The image runs as appuser uid/gid 999.  Its sole writable mount is the
# research-data boundary, so feature materialization cannot alter runtime
# state, a simulated execution ledger, or an order path.
install -d -o 999 -g 999 -m 0775 "${FEATURE_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"
chown 999:999 "${FEATURE_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"
chmod 0775 "${FEATURE_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"

docker run --rm \
  --name "autobot-research-derivatives-features-${RUN_ID}" \
  --label "autobot.component=research-derivatives-feature-snapshot" \
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
  --env TZ=UTC \
  --volume "${REPO_DIR}/data/research:/app/data/research" \
  "${IMAGE}" \
  python -m autobot.v2.cli materialize-derivatives-feature-snapshot \
    --run-id "${RUN_ID}" \
    --derivatives-manifest "/app/data/research/manifests/${DERIVATIVES_MANIFEST}" \
    --as-of-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --output-dir /app/data/research/canonical/derivatives_features \
    --manifest-dir /app/data/research/manifests \
    --report-dir /app/data/research/reports/derivatives_feature_snapshot \
    --provenance-scope forward_capture_only
