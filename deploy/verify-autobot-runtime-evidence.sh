#!/usr/bin/env bash
set -euo pipefail

# Emit one non-secret RuntimeDeploymentEvidence JSON record after a controlled
# rebuild. This script is read-only: it never changes Git, Docker, flags,
# data, strategies or orders. A missing or unsafe fact is an error, not a
# partially green deployment report.

REPO_DIR="${AUTOBOT_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CONTAINER_NAME="${AUTOBOT_CONTAINER_NAME:-autobot-v2}"
HEALTH_WAIT_SECONDS="${AUTOBOT_DEPLOY_HEALTH_WAIT_SECONDS:-90}"

if ! [[ "${HEALTH_WAIT_SECONDS}" =~ ^[0-9]+$ ]]; then
  echo "AUTOBOT_DEPLOY_HEALTH_WAIT_SECONDS must be a non-negative integer." >&2
  exit 1
fi

SOURCE_COMMIT="$(git -C "${REPO_DIR}" rev-parse --verify HEAD)"
GITHUB_COMMIT="$(git -C "${REPO_DIR}" rev-parse --verify refs/remotes/origin/master)"
if [[ "${SOURCE_COMMIT}" != "${GITHUB_COMMIT}" ]]; then
  echo "Refusing deployment evidence: VPS checkout is not aligned with origin/master." >&2
  exit 1
fi

CONTAINER_ID="$(docker ps -q --filter "name=^/${CONTAINER_NAME}$")"
if [[ -z "${CONTAINER_ID}" ]]; then
  echo "Refusing deployment evidence: AUTOBOT container is not running." >&2
  exit 1
fi

EXPECTED_IMAGE_ID="$(docker image inspect --format '{{.Id}}' projet_autobot-autobot 2>/dev/null || true)"
CONTAINER_IMAGE_ID="$(docker inspect --format '{{.Image}}' "${CONTAINER_ID}" 2>/dev/null || true)"
IMAGE_COMMIT="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' projet_autobot-autobot 2>/dev/null || true)"
CONTAINER_STATUS="$(docker inspect --format '{{.State.Status}}' "${CONTAINER_ID}" 2>/dev/null || true)"

if [[ "${CONTAINER_STATUS}" != "running" || -z "${EXPECTED_IMAGE_ID}" || "${CONTAINER_IMAGE_ID}" != "${EXPECTED_IMAGE_ID}" ]]; then
  echo "Refusing deployment evidence: running container does not use the expected AUTOBOT image." >&2
  exit 1
fi
if [[ "${IMAGE_COMMIT}" != "${SOURCE_COMMIT}" ]]; then
  echo "Refusing deployment evidence: image revision does not match the source commit." >&2
  exit 1
fi

deadline=$((SECONDS + HEALTH_WAIT_SECONDS))
health_payload=""
while :; do
  if health_payload="$(curl --fail --silent --max-time 5 http://127.0.0.1:8080/health)"; then
    container_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "${CONTAINER_ID}" 2>/dev/null || true)"
    if [[ "${container_health}" == "healthy" ]]; then
      break
    fi
  fi
  if (( SECONDS >= deadline )); then
    echo "Refusing deployment evidence: health endpoint/container did not become healthy." >&2
    exit 1
  fi
  sleep 2
done

websocket_connected="$(printf '%s' "${health_payload}" | python3 -c '
import json
import sys
try:
    payload = json.load(sys.stdin)
    components = payload.get("components") if isinstance(payload, dict) else {}
    websocket = components.get("websocket") if isinstance(components, dict) else None
    print("true" if payload.get("status") == "healthy" and websocket == "connected" else "false")
except (TypeError, ValueError, json.JSONDecodeError):
    print("false")
')"
if [[ "${websocket_connected}" != "true" ]]; then
  echo "Refusing deployment evidence: health payload does not prove a connected WebSocket." >&2
  exit 1
fi

# Filter only known non-secret safety flags. Do not print or retain the full
# container environment, which may contain dashboard credentials.
safety_environment="$(
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${CONTAINER_ID}" |
    awk -F= '
      $1 == "AUTOBOT_OBSERVATION_ONLY_RUNTIME" ||
      $1 == "PAPER_TRADING" ||
      $1 == "PAPER_EXECUTION_ADAPTER_ENABLED" ||
      $1 == "PAPER_EXECUTION_ROUTER_ENABLED" ||
      $1 == "PAPER_TEST_TRADING_ENABLED" ||
      $1 == "COLONY_AUTO_LIVE_PROMOTION" ||
      $1 == "STRATEGY_ROUTER_LIVE_ENABLED" ||
      $1 == "LIVE_TRADING_CONFIRMATION" { print }
    '
)"

require_safety_flag() {
  local expected="$1"
  if ! grep -Fxq "${expected}" <<<"${safety_environment}"; then
    echo "Refusing deployment evidence: missing required safe runtime flag ${expected%%=*}." >&2
    exit 1
  fi
}

require_safety_flag "AUTOBOT_OBSERVATION_ONLY_RUNTIME=true"
require_safety_flag "PAPER_TRADING=false"
require_safety_flag "PAPER_EXECUTION_ADAPTER_ENABLED=false"
require_safety_flag "PAPER_EXECUTION_ROUTER_ENABLED=false"
require_safety_flag "PAPER_TEST_TRADING_ENABLED=false"
require_safety_flag "COLONY_AUTO_LIVE_PROMOTION=false"
require_safety_flag "STRATEGY_ROUTER_LIVE_ENABLED=false"
require_safety_flag "LIVE_TRADING_CONFIRMATION=false"

observed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '{"source_commit":"%s","github_commit":"%s","vps_commit":"%s","container_revision":"%s","observed_at":"%s","container_healthy":true,"health_endpoint_healthy":true,"websocket_connected":true,"observation_only_runtime":true,"paper_capital_disabled":true,"live_disabled":true,"automatic_promotion_disabled":true}\n' \
  "${SOURCE_COMMIT}" "${GITHUB_COMMIT}" "${SOURCE_COMMIT}" "${IMAGE_COMMIT}" "${observed_at}"
