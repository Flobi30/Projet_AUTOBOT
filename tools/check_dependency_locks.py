#!/usr/bin/env python3
"""Validate Python dependency lockfiles are pinned and up to date."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_SPECS = [
    (ROOT / "requirements/runtime.in", ROOT / "requirements/runtime.txt"),
    (ROOT / "requirements/api.in", ROOT / "requirements/api.txt"),
    (ROOT / "requirements/tests.in", ROOT / "requirements/tests.txt"),
    (ROOT / "requirements/requirements.in", ROOT / "requirements.txt"),
]

SECONDARY_LOCK_REFERENCES = {
    ROOT / "src/autobot/v2/api/requirements.txt": "-r ../../../../requirements/api.txt",
    ROOT / "src/autobot/v2/tests/requirements.txt": "-r ../../../../requirements/tests.txt",
}


def _is_pinned_requirement(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return True
    if stripped.startswith(("-r", "--")):
        return True
    return "==" in stripped


def validate_pinning() -> list[str]:
    errors: list[str] = []
    for _, lockfile in LOCK_SPECS:
        if not lockfile.exists():
            errors.append(f"Missing lockfile: {lockfile.relative_to(ROOT)}")
            continue

        for lineno, line in enumerate(lockfile.read_text(encoding="utf-8").splitlines(), start=1):
            if not _is_pinned_requirement(line):
                rel = lockfile.relative_to(ROOT)
                errors.append(f"Unpinned dependency in {rel}:{lineno} -> {line.strip()}")
    return errors


def validate_secondary_requirements() -> list[str]:
    errors: list[str] = []
    for req_file, expected_ref in SECONDARY_LOCK_REFERENCES.items():
        if not req_file.exists():
            errors.append(f"Missing requirements file: {req_file.relative_to(ROOT)}")
            continue

        references = [
            line.strip()
            for line in req_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        if references != [expected_ref]:
            rel = req_file.relative_to(ROOT)
            errors.append(
                f"{rel} must only reference '{expected_ref}' (found: {references or 'no requirement lines'})"
            )

        for lineno, line in enumerate(req_file.read_text(encoding="utf-8").splitlines(), start=1):
            if not _is_pinned_requirement(line):
                rel = req_file.relative_to(ROOT)
                errors.append(f"Unpinned dependency in {rel}:{lineno} -> {line.strip()}")
    return errors


def validate_regeneration() -> int:
    for source, lockfile in LOCK_SPECS:
        cmd = [
            sys.executable,
            "-m",
            "piptools",
            "compile",
            "--quiet",
            "--resolver=backtracking",
            "--output-file",
            str(lockfile.relative_to(ROOT)),
            str(source.relative_to(ROOT)),
        ]
        result = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            print(f"Failed to compile {source.relative_to(ROOT)}", file=sys.stderr)
            return 1

    diff = subprocess.run(
        ["git", "diff", "--exit-code", "--", "requirements", "requirements.txt"],
        cwd=ROOT,
        check=False,
    )
    if diff.returncode != 0:
        print("Dependency lockfiles are stale. Run pip-compile and commit updated lockfiles.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    pin_errors = validate_pinning()
    pin_errors.extend(validate_secondary_requirements())
    if pin_errors:
        print("\n".join(pin_errors), file=sys.stderr)
        return 1

    return validate_regeneration()


if __name__ == "__main__":
    raise SystemExit(main())
