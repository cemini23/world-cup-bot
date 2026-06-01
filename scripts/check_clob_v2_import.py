#!/usr/bin/env python3
"""Fail if clob_live.py imports archived py-clob-client V1."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLOB_LIVE = ROOT / "world_cup_bot" / "clob_live.py"
FORBIDDEN = re.compile(r"\bpy_clob_client\b(?!_v2)")


def main() -> int:
    text = CLOB_LIVE.read_text(encoding="utf-8")
    hits: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if "py_clob_client_v2" in line:
            continue
        if FORBIDDEN.search(line):
            hits.append(f"{i}:{line.strip()}")
    if hits:
        print("FAIL: clob_live.py must use py_clob_client_v2 only", file=sys.stderr)
        for hit in hits:
            print(hit, file=sys.stderr)
        return 1
    print("OK: clob_live.py uses py-clob-client-v2 imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
