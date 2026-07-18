#!/usr/bin/env bash
set -euo pipefail

# Build and recreate AUTOBOT from a committed source tree while embedding the
# revision in the image label.  Research jobs use the label to reject stale or
# unverifiable images before collecting data or writing research evidence.
#
# This helper intentionally does not inspect .env files or print environment
# variables.  It rebuilds only the AUTOBOT service; it never enables paper or
# live execution flags.

REPO_DIR="${AUTOBOT_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BUILD_INPUT_PATHS=(
  Dockerfile
  Dockerfile.pypy
  .dockerignore
  docker-compose.yml
  requirements.txt
  .env.example
  src
  dashboard
  docs/research
  docs/architecture
)

if ! git -C "${REPO_DIR}" diff --quiet -- "${BUILD_INPUT_PATHS[@]}" \
  || ! git -C "${REPO_DIR}" diff --cached --quiet -- "${BUILD_INPUT_PATHS[@]}"; then
  echo "Refusing to build AUTOBOT from tracked uncommitted build inputs." >&2
  exit 1
fi
if [[ -n "$(git -C "${REPO_DIR}" ls-files --others --exclude-standard -- "${BUILD_INPUT_PATHS[@]}")" ]]; then
  echo "Refusing to build AUTOBOT from untracked build inputs." >&2
  exit 1
fi

SOURCE_COMMIT="$(git -C "${REPO_DIR}" rev-parse --verify HEAD)"

AUTOBOT_BUILD_COMMIT="${SOURCE_COMMIT}" \
  docker compose --project-directory "${REPO_DIR}" build autobot

docker compose --project-directory "${REPO_DIR}" up -d --no-deps autobot

IMAGE_COMMIT="$(docker image inspect --format '{{ index .Config.Labels \"org.opencontainers.image.revision\" }}' projet_autobot-autobot 2>/dev/null || true)"
if [[ "${IMAGE_COMMIT}" != "${SOURCE_COMMIT}" ]]; then
  echo "AUTOBOT image provenance verification failed after build." >&2
  exit 1
fi

echo "AUTOBOT image built and recreated with commit ${SOURCE_COMMIT}."
