#!/usr/bin/env bash
set -euo pipefail

# This batch job reads only canonical public top-of-book evidence. It can write
# a compact research report, but cannot see runtime state, secrets, logs, or
# any order-routing surface. The report is descriptive and non-authorizing.
REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
RUN_ID="${AUTOBOT_MICROSTRUCTURE_PROFILE_RUN_ID:-microstructure_profile_$(date -u +%Y_%m_%dT%H_%M_%SZ)}"
LOCK_PATH="${AUTOBOT_MICROSTRUCTURE_PROFILE_LOCK_PATH:-/run/lock/autobot-research-microstructure-profile.lock}"
MEMORY_LIMIT="${AUTOBOT_MICROSTRUCTURE_PROFILE_MEMORY_LIMIT:-256m}"
CPU_LIMIT="${AUTOBOT_MICROSTRUCTURE_PROFILE_CPU_LIMIT:-0.20}"
MIN_SAMPLES_PER_SYMBOL="${AUTOBOT_MICROSTRUCTURE_PROFILE_MIN_SAMPLES_PER_SYMBOL:-96}"
MIN_DISTINCT_UTC_HOURS="${AUTOBOT_MICROSTRUCTURE_PROFILE_MIN_DISTINCT_UTC_HOURS:-12}"
MIN_OBSERVATION_SPAN_SECONDS="${AUTOBOT_MICROSTRUCTURE_PROFILE_MIN_OBSERVATION_SPAN_SECONDS:-86400}"

CANONICAL_ROOT="${REPO_DIR}/data/research/canonical/microstructure"
PROFILE_REPORT_DIR="${REPO_DIR}/data/research/reports/canonical_microstructure_profiles"

exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  echo "AUTOBOT canonical microstructure profile is already running; skipping ${RUN_ID}."
  exit 0
fi

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "AUTOBOT microstructure profile image is unavailable: ${IMAGE}" >&2
  exit 1
fi

SOURCE_COMMIT="$(git -C "${REPO_DIR}" rev-parse HEAD)"
IMAGE_COMMIT="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "${IMAGE}" 2>/dev/null || true)"
if [[ ! "${IMAGE_COMMIT}" =~ ^[0-9a-f]{40}$ || "${IMAGE_COMMIT}" != "${SOURCE_COMMIT}" ]]; then
  echo "AUTOBOT canonical microstructure profile blocked: image provenance mismatch (source=${SOURCE_COMMIT}, image=${IMAGE_COMMIT:-unverified})." >&2
  exit 1
fi

# The input tree is mounted read-only and is never chmod/chown touched here.
# Only this dedicated report directory is writable by the non-root image user,
# preserving the source snapshots and their host ownership.
if [[ ! -d "${CANONICAL_ROOT}" ]]; then
  echo "AUTOBOT canonical microstructure profile blocked: canonical input is missing: ${CANONICAL_ROOT}" >&2
  exit 1
fi
install -d -o 999 -g 999 -m 0775 "${PROFILE_REPORT_DIR}"
chown 999:999 "${PROFILE_REPORT_DIR}"
chmod 0775 "${PROFILE_REPORT_DIR}"

exec docker run --rm \
  --name "autobot-research-microstructure-profile-${RUN_ID}" \
  --label "autobot.component=research-microstructure-profile" \
  --label "autobot.job=research-microstructure-profile" \
  --network none \
  --no-healthcheck \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  --security-opt no-new-privileges \
  --cap-drop ALL \
  --memory "${MEMORY_LIMIT}" \
  --cpus "${CPU_LIMIT}" \
  --env PYTHONPATH=/app/src \
  --env PYTHONUNBUFFERED=1 \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env HOME=/tmp \
  --env TZ=UTC \
  --volume "${REPO_DIR}/data/research:/app/data/research:ro" \
  --volume "${PROFILE_REPORT_DIR}:/app/data/research/reports/canonical_microstructure_profiles" \
  "${IMAGE}" \
  python -m autobot.v2.cli profile-canonical-microstructure \
    --run-id "${RUN_ID}" \
    --canonical-paths /app/data/research/canonical/microstructure \
    --output-dir /app/data/research/reports/canonical_microstructure_profiles \
    --min-samples-per-symbol "${MIN_SAMPLES_PER_SYMBOL}" \
    --min-distinct-utc-hours "${MIN_DISTINCT_UTC_HOURS}" \
    --min-observation-span-seconds "${MIN_OBSERVATION_SPAN_SECONDS}"
