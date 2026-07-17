#!/usr/bin/env bash
set -euo pipefail

# This is an isolated public-market-data job.  It deliberately does not mount
# .env, secrets, the runtime logs, or any order-routing surface.
REPO_DIR="${AUTOBOT_REPO_DIR:-/opt/Projet_AUTOBOT}"
IMAGE="${AUTOBOT_RESEARCH_IMAGE:-projet_autobot-autobot}"
COLLECTION_MODE="${AUTOBOT_DERIVATIVES_COLLECTION_MODE:-ticker}"
RUN_ID="${AUTOBOT_DERIVATIVES_RUN_ID:-derivatives_${COLLECTION_MODE}_$(date -u +%Y_%m_%dT%H_%M_%SZ)}"
LOCK_PATH="${AUTOBOT_DERIVATIVES_LOCK_PATH:-/run/lock/autobot-research-derivatives.lock}"
MEMORY_LIMIT="${AUTOBOT_DERIVATIVES_MEMORY_LIMIT:-512m}"
CPU_LIMIT="${AUTOBOT_DERIVATIVES_CPU_LIMIT:-0.25}"

RAW_DIR="${REPO_DIR}/data/research/raw/kraken_futures"
CANONICAL_DIR="${REPO_DIR}/data/research/canonical/derivatives"
MANIFEST_DIR="${REPO_DIR}/data/research/manifests"
REPORT_DIR="${REPO_DIR}/data/research/reports/kraken_futures_derivatives"

exec 9>"${LOCK_PATH}"
if ! flock -n 9; then
  echo "AUTOBOT derivatives collection is already running; skipping ${RUN_ID}."
  exit 0
fi

if ! docker image inspect "${IMAGE}" >/dev/null 2>&1; then
  echo "Research image is unavailable: ${IMAGE}" >&2
  exit 1
fi

# The image uses appuser uid/gid 999. Keep all mutable outputs below the
# research data boundary, outside the runtime state DB and order paths.
install -d -o 999 -g 999 -m 0775 "${RAW_DIR}" "${CANONICAL_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"
chown 999:999 "${RAW_DIR}" "${CANONICAL_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"
chmod 0775 "${RAW_DIR}" "${CANONICAL_DIR}" "${MANIFEST_DIR}" "${REPORT_DIR}"

case "${COLLECTION_MODE}" in
  ticker)
    COLLECTION_FLAGS=(--skip-funding --skip-candles)
    ;;
  funding_refresh)
    # Funding rows are only marked forward-captured when the public endpoint
    # returns a fresh timestamp inside this explicit budget. Older rows remain
    # historical research data.
    COLLECTION_FLAGS=(--skip-tickers --skip-candles --forward-capture-max-lag-seconds 7200)
    ;;
  open_interest_refresh)
    # A deliberately small overlap absorbs scheduler jitter and is compacted
    # deterministically. It remains an explicit historical query and cannot
    # prove runtime feature parity by itself.
    OI_END="$(date -u +%Y-%m-%dT%H:00:00+00:00)"
    OI_START="$(date -u -d '3 hours ago' +%Y-%m-%dT%H:00:00+00:00)"
    COLLECTION_FLAGS=(
      --skip-funding --skip-tickers --skip-candles
      --collect-open-interest-history
      --open-interest-backfill-start-at "${OI_START}"
      --open-interest-backfill-end-at "${OI_END}"
      --open-interest-interval-seconds 3600
      --open-interest-max-pages-per-symbol 1
      --forward-capture-max-lag-seconds 900
    )
    ;;
  future_basis_refresh)
    # A bounded overlap absorbs scheduler jitter.  These are exchange-provided
    # same-contract buckets, collected outside the AUTOBOT runtime and never
    # treated as an execution signal on their own.
    BASIS_END="$(date -u +%Y-%m-%dT%H:00:00+00:00)"
    BASIS_START="$(date -u -d '3 hours ago' +%Y-%m-%dT%H:00:00+00:00)"
    COLLECTION_FLAGS=(
      --skip-funding --skip-tickers --skip-candles
      --collect-future-basis-history
      --future-basis-backfill-start-at "${BASIS_START}"
      --future-basis-backfill-end-at "${BASIS_END}"
      --future-basis-interval-seconds 3600
      --future-basis-max-pages-per-symbol 1
      --forward-capture-max-lag-seconds 900
    )
    ;;
  *)
    echo "Unsupported derivatives collection mode: ${COLLECTION_MODE}" >&2
    exit 1
    ;;
esac

exec docker run --rm \
  --name "autobot-research-derivatives-${RUN_ID}" \
  --label "autobot.component=research-derivatives-collection" \
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
  python -m autobot.v2.cli collect-kraken-futures-derivatives \
    --run-id "${RUN_ID}" \
    --assets "BTC,ETH,SOL,XRP,ADA,LINK" \
    --max-symbols 6 \
    "${COLLECTION_FLAGS[@]}" \
    --raw-dir /app/data/research/raw/kraken_futures \
    --canonical-dir /app/data/research/canonical/derivatives \
    --manifest-dir /app/data/research/manifests \
    --report-dir /app/data/research/reports/kraken_futures_derivatives \
    --raw-retention-days 7 \
    --timeout-seconds 20
