"""Tests for pmxt → shock tape ETL exporter."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[0] / "fixtures" / "shock_replay" / "pmxt_sample.jsonl"


def test_export_pmxt_shock_tapes(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "shock_backtest" / "export_pmxt_shock_tapes.py"
    out = tmp_path / "tapes"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            str(FIXTURE),
            "--out-dir",
            str(out),
            "--format",
            "pmxt_event",
            "--per-slug",
        ],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    combined = out / "combined.jsonl"
    assert combined.is_file()
    lines = [json.loads(ln) for ln in combined.read_text().splitlines() if ln.strip()]
    slugs = {row["slug"] for row in lines}
    assert "epl-man-united-win-2025-04-01" in slugs
    assert "will-brazil-advance-to-knockout" not in slugs
    assert (out / "by_slug").is_dir()
