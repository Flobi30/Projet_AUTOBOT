#!/usr/bin/env bash
set -euo pipefail

# Canonical frontend location is dashboard/src only.
# Fail if TSX/JSX pages are committed at repository root.
invalid_files=$(find . -maxdepth 1 -type f \( -name '*.tsx' -o -name '*.jsx' \) | sort)

if [[ -n "$invalid_files" ]]; then
  echo "❌ React page/component files detected at repository root."
  echo "Move them under dashboard/src (e.g. dashboard/src/pages or dashboard/src/components)."
  echo
  echo "$invalid_files"
  exit 1
fi

echo "✅ Frontend path check passed (no root-level React TSX/JSX files)."
