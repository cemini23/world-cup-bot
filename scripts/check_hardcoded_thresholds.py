#!/usr/bin/env python3
"""Fail if price/mid thresholds are hardcoded in hot-path modules (config/*.yaml only)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOT_PATH = (
    ROOT / "world_cup_bot" / "scanner.py",
    ROOT / "world_cup_bot" / "quoter.py",
    ROOT / "world_cup_bot" / "fill_handler.py",
)
PATTERN = re.compile(r"(mid\s*[><=!]+\s*0\.|>\s*0\.90|<\s*0\.10)")


def main() -> int:
    hits: list[str] = []
    for path in HOT_PATH:
        if not path.is_file():
            print(f"FAIL: missing hot-path file {path}", file=sys.stderr)
            return 1
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if PATTERN.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()}")
    if hits:
        print(
            "FAIL: hardcoded mid/threshold in hot-path — "
            "move to config/operating.yaml or config/conviction.yaml",
            file=sys.stderr,
        )
        for hit in hits:
            print(hit, file=sys.stderr)
        return 1
    print("OK: no hardcoded mid thresholds in hot-path modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
