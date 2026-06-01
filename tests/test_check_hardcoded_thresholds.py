"""Tests for scripts/check_hardcoded_thresholds.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_hardcoded_thresholds.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_hardcoded_thresholds", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_threshold_guard_ok_on_repo():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr.decode()
    assert b"OK:" in proc.stdout


def test_threshold_guard_ignores_hash_comments():
    guard = _load_guard()
    assert not guard.line_matches_threshold("# mid > 0.90 is loaded from config/operating.yaml")
    assert guard.line_matches_threshold("if mid > 0.90:")
