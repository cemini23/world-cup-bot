"""Tests for K107 liquidity posture helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from world_cup_bot.k107_posture import (
    K107PostureConfig,
    LpSafetyDrConfig,
    clamp_notional_multiplier,
    load_k107_posture,
    lp_safety_due,
    mark_lp_safety_run,
)


def test_load_k107_posture_defaults(tmp_path: Path):
    cfg = load_k107_posture(tmp_path / "missing.yaml")
    assert cfg.block_volume_based_cap_scaling is True


def test_clamp_notional_multiplier_blocks_volume_scale():
    cfg = K107PostureConfig(block_volume_based_cap_scaling=True)
    assert clamp_notional_multiplier(1.0, volume_scale=1.5, cfg=cfg) == 1.0
    assert clamp_notional_multiplier(0.8, volume_scale=1.2, cfg=cfg) == 0.8


def test_lp_safety_due_when_marker_missing(tmp_path: Path, monkeypatch):
    cfg = K107PostureConfig(
        lp_safety_dr=LpSafetyDrConfig(last_run_marker=str(tmp_path / "marker.txt"))
    )
    monkeypatch.setattr(
        "world_cup_bot.k107_posture.resolve_project_path",
        lambda p: tmp_path / "marker.txt",
    )
    assert lp_safety_due(cfg) is True


def test_lp_safety_not_due_after_mark(tmp_path: Path, monkeypatch):
    marker = tmp_path / "marker.txt"
    cfg = K107PostureConfig(
        lp_safety_dr=LpSafetyDrConfig(last_run_marker=str(marker))
    )
    monkeypatch.setattr(
        "world_cup_bot.k107_posture.resolve_project_path",
        lambda p: marker,
    )
    now = datetime(2026, 6, 9, tzinfo=UTC)
    mark_lp_safety_run(cfg, now=now)
    assert lp_safety_due(cfg, now=now + timedelta(days=1)) is False
    assert lp_safety_due(cfg, now=now + timedelta(days=8)) is True
