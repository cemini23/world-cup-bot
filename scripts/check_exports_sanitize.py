#!/usr/bin/env python3
"""Fail if exports/ audit artifacts leak local paths or full tracebacks."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "exports"

HOME_PATH = re.compile(r"/(?:Users|home)/[^\s\"']+")
TRACEBACK = re.compile(r"Traceback \(most recent call last\)")


def main() -> int:
    if not EXPORTS.is_dir():
        print("OK: no exports/ directory")
        return 0
    hits: list[str] = []
    for path in sorted(EXPORTS.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT)
        if HOME_PATH.search(text):
            hits.append(f"{rel}: absolute home path")
        if TRACEBACK.search(text):
            hits.append(f"{rel}: committed Python traceback")
    if hits:
        print("FAIL: exports/ must use repo-relative paths and one-line errors only", file=sys.stderr)
        for hit in hits:
            print(hit, file=sys.stderr)
        return 1
    print("OK: exports/ sanitize check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
