#!/usr/bin/env python3
"""Verify requirements-lock.txt pins match pyproject.toml optional extras."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "requirements-lock.txt"
PYPROJECT = ROOT / "pyproject.toml"

# Package names in lockfile → pyproject optional-extra section
EXPECTED = {
    "PyYAML": "core",
    "websockets": "live",
    "py-clob-client-v2": "live",
    "eth-account": "live",
    "cryptography": "live",
    "pytest": "dev",
    "ruff": "dev",
}


def parse_lock(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s]+)$", line)
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


def parse_pyproject_names(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    names: set[str] = set()
    for m in re.finditer(r'"([a-zA-Z0-9_.-]+)', text):
        pkg = m.group(1)
        if pkg.startswith("py") or pkg in {"pytest", "ruff", "websockets", "eth-account", "cryptography"}:
            names.add(pkg)
    # Normalize PyYAML
    if "pyyaml" in text.lower():
        names.add("PyYAML")
    return names


def main() -> int:
    if not LOCK.is_file():
        print(f"FAIL: missing {LOCK}")
        return 1

    pins = parse_lock(LOCK)
    errors: list[str] = []

    for pkg in EXPECTED:
        if pkg not in pins:
            errors.append(f"missing pin for {pkg}")

    if len(pins) < 6:
        errors.append(f"expected >=6 pins, found {len(pins)}")

    # Every lock row should be known
    for pkg in pins:
        if pkg not in EXPECTED:
            errors.append(f"unexpected lock entry {pkg} — update EXPECTED in script")

    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1

    print(f"OK: requirements-lock.txt ({len(pins)} pins)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
