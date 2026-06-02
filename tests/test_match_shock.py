"""Tests for Module 8 match-shock detection and ladder planning."""

from __future__ import annotations

from pathlib import Path

import pytest

from world_cup_bot.match_shock import (
    BookLevel,
    PriceTick,
    ShockContext,
    bucket_key,
    build_ladder,
    compute_percentiles,
    detect_shock,
    plan_ladder,
    simulate_paper_fill,
    simulate_recovery_pnl,
    slug_in_scope,
)
from world_cup_bot.match_shock_config import load_match_shock_config

FIXTURE = Path(__file__).resolve().parents[0] / "fixtures" / "shock_replay" / "sample_trades.jsonl"


@pytest.fixture
def cfg():
    return load_match_shock_config()


def test_detect_shock_positive():
    ticks = (
        PriceTick(ts_ms=0, price=0.30),
        PriceTick(ts_ms=60_000, price=0.28),
        PriceTick(ts_ms=120_000, price=0.20),
    )
    result = detect_shock(ticks, min_drop_pct=0.15, min_drop_abs=0.08)
    assert result.shock is True
    assert result.peak == pytest.approx(0.30)
    assert result.floor == pytest.approx(0.20)
    assert result.depth == pytest.approx(0.10)


def test_detect_shock_negative_small_move():
    ticks = (
        PriceTick(ts_ms=0, price=0.50),
        PriceTick(ts_ms=60_000, price=0.48),
    )
    result = detect_shock(ticks, min_drop_pct=0.15, min_drop_abs=0.08)
    assert result.shock is False


def test_bucket_key_epl_underdog(cfg):
    ctx = ShockContext(
        slug="epl-man-united-win",
        pre_price=0.30,
        bids=(BookLevel(0.29, 50), BookLevel(0.28, 50)),
        elapsed_ms=35 * 60_000,
        goal_diff=0,
    )
    key = bucket_key(ctx, cfg.classifiers)
    assert key == "deep|underdog|top_heavy|mid|level"


def test_compute_percentiles():
    pcts = compute_percentiles((4, 5, 6, 7, 8, 10, 12, 15, 20, 25), (50, 75, 90, 95))
    assert pcts[50] == pytest.approx(9.0, rel=0.05)
    assert pcts[75] == pytest.approx(14.0, rel=0.05)


def test_plan_ladder_uses_defaults_on_thin_bucket(cfg):
    ctx = ShockContext(
        slug="epl-test",
        pre_price=0.30,
        bids=(),
        elapsed_ms=35 * 60_000,
        goal_diff=0,
    )
    plan = plan_ladder(ctx, {}, cfg)
    assert plan.bucket_key.startswith("deep|")
    assert len(plan.orders) == 4
    assert plan.orders[-1].limit_price < plan.orders[0].limit_price


def test_build_ladder_weights_sum(cfg):
    pcts = {50: 8.0, 75: 12.0, 90: 16.0, 95: 20.0}
    orders = build_ladder(0.30, pcts, cfg.ladder)
    assert sum(o.size_usd for o in orders) == pytest.approx(cfg.ladder.capital_usd)


def test_simulate_paper_fill_deepest_rung():
    from world_cup_bot.match_shock import LadderOrder, LadderPlan

    orders = (
        LadderOrder(50, 0.22, 5.0, 0.1),
        LadderOrder(90, 0.14, 15.0, 0.3),
    )
    plan = LadderPlan("k", 0.30, {}, orders, 0.26)
    fill = simulate_paper_fill(plan, 0.14)
    assert fill is not None
    assert fill.percentile == 90


def test_simulate_recovery_pnl():
    from world_cup_bot.match_shock import LadderOrder

    fill = LadderOrder(90, 0.14, 15.0, 0.3)
    pnl = simulate_recovery_pnl(fill, 0.18)
    assert pnl > 0


def test_slug_in_scope_blocks_advance(cfg):
    assert slug_in_scope("will-brazil-advance-to-knockout", cfg) is False
    assert slug_in_scope("fifa-world-cup-usa-vs-mexico", cfg) is True


def test_fixture_jsonl_backtest_script(tmp_path: Path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "shock_backtest" / "run_bucket_backtest.py"
    out = tmp_path / "dist.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            str(FIXTURE),
            "--out-distributions",
            str(out),
            "--replay",
        ],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
