#!/usr/bin/env python3
"""Validate that each required env var documented in README exists in .env.example."""

from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")
ENV_EXAMPLE = Path(".env.example")


def parse_required_vars_from_readme(readme_text: str) -> list[str]:
    required: list[str] = []
    in_table = False

    for raw_line in readme_text.splitlines():
        line = raw_line.strip()
        if line.startswith("| Variable | Obligatoire |"):
            in_table = True
            continue
        if in_table and (not line or not line.startswith("|")):
            break
        if not in_table:
            continue

        if line.startswith("|---"):
            continue

        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue

        var_col, required_col = cols[0], cols[1].lower()
        var_match = re.search(r"`([A-Z0-9_]+)`", var_col)
        if not var_match:
            continue

        if required_col.startswith("oui"):
            required.append(var_match.group(1))

    return required


def parse_env_keys(env_text: str) -> set[str]:
    keys: set[str] = set()
    for raw_line in env_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if re.fullmatch(r"[A-Z0-9_]+", key):
            keys.add(key)
    return keys


def main() -> int:
    readme_text = README.read_text(encoding="utf-8")
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")

    required_vars = parse_required_vars_from_readme(readme_text)
    env_keys = parse_env_keys(env_text)

    if not required_vars:
        print("ERROR: no required variables found in README table")
        return 1

    missing = [name for name in required_vars if name not in env_keys]
    if missing:
        print("ERROR: required vars documented in README but missing in .env.example:")
        for name in missing:
            print(f" - {name}")
        return 1

    print(f"OK: {len(required_vars)} required vars documented and present in .env.example")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
