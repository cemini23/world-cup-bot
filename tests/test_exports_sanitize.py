"""Tests for scripts/check_exports_sanitize.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_exports_sanitize.py"


def test_exports_sanitize_ok_on_repo():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr.decode()
    assert b"OK:" in proc.stdout
