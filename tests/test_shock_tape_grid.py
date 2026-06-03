"""Tests for shock_tape utilities and bucket grid."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from world_cup_bot.match_shock_config import load_match_shock_config
from world_cup_bot.shock_tape import group_by_slug, load_ticks, replay_paper, scan_shocks

FIXTURE = Path(__file__).resolve().parents[0] / "fixtures" / "shock_replay" / "sample_trades.jsonl"
ROOT = Path(__file__).resolve().parents[1]


def test_load_ticks_and_scan():
    cfg = load_match_shock_config()
    ticks = load_ticks(FIXTURE)
    assert ticks
    by_slug = group_by_slug(ticks)
    shocks = scan_shocks(next(iter(by_slug.values())), cfg)
    assert isinstance(shocks, list)


def test_replay_paper():
    cfg = load_match_shock_config()
    ticks = load_ticks(FIXTURE)
    by_slug = group_by_slug(ticks)
    stats = replay_paper(by_slug, {}, cfg)
    assert "win_rate" in stats


def test_run_bucket_grid_script(tmp_path: Path):
    script = ROOT / "scripts" / "shock_backtest" / "run_bucket_grid.py"
    out_dir = tmp_path / "grid"
    proc = subprocess.run(
        [sys.executable, str(script), str(FIXTURE), "--out-dir", str(out_dir)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert (out_dir / "replay_report.json").is_file()
    assert (out_dir / "replay_report.md").is_file()
