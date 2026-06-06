"""Tests for K102 streak-based dynamic sizing."""

from __future__ import annotations

from datetime import UTC, datetime

from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.risk_gates_config import DynamicSizingConfig
from world_cup_bot.streak_sizing import (
    dynamic_size_multiplier,
    streak_state_from_ledger,
    trailing_streaks,
)


def _spec() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        strategy_key="pm_wc_advance_lp",
        version_id="wc_advance_lp_v5",
        deployed_at=datetime.now(UTC),
        note="",
        legacy_version_ids=frozenset(),
    )


def _cfg(**overrides) -> DynamicSizingConfig:
    base = dict(
        enabled=True,
        loss_reduction_pct=0.20,
        loss_streak_threshold=2,
        win_increase_pct=0.10,
        win_streak_threshold=3,
        win_streak_cap=5,
        min_size_multiplier=0.25,
        max_size_multiplier=1.25,
    )
    base.update(overrides)
    return DynamicSizingConfig(**base)


def test_trailing_streaks_empty():
    assert trailing_streaks([]) == (0, 0)


def test_trailing_streaks_losses_at_tail():
    assert trailing_streaks([-1.0, 2.0, -3.0, -4.0]) == (0, 2)


def test_trailing_streaks_wins_at_tail():
    assert trailing_streaks([-1.0, 2.0, 3.0]) == (2, 0)


def test_no_reduction_at_loss_threshold():
    mult = dynamic_size_multiplier(_cfg(), consecutive_wins=0, consecutive_losses=2)
    assert mult == 1.0


def test_loss_reduction_after_threshold():
    mult = dynamic_size_multiplier(_cfg(), consecutive_wins=0, consecutive_losses=3)
    assert abs(mult - 0.8) < 1e-6


def test_loss_reduction_compounds():
    mult = dynamic_size_multiplier(_cfg(), consecutive_wins=0, consecutive_losses=5)
    assert abs(mult - 0.8**3) < 1e-6


def test_win_increase_after_threshold():
    mult = dynamic_size_multiplier(_cfg(), consecutive_wins=4, consecutive_losses=0)
    assert abs(mult - 1.1) < 1e-6


def test_win_increase_capped():
    mult = dynamic_size_multiplier(_cfg(), consecutive_wins=20, consecutive_losses=0)
    assert mult == 1.25


def test_min_multiplier_floor():
    mult = dynamic_size_multiplier(
        _cfg(min_size_multiplier=0.5),
        consecutive_wins=0,
        consecutive_losses=10,
    )
    assert mult == 0.5


def test_streak_state_from_ledger(tmp_path):
    from world_cup_bot import ledger

    path = tmp_path / "l.jsonl"
    spec = _spec()
    for pnl in (-10.0, -20.0, 30.0):
        ledger.append_row(
            path,
            ledger.LedgerRow(
                event="order_fill",
                logic_version=spec.version_id,
                strategy_key=spec.strategy_key,
                timestamp="2026-06-06T12:00:00+00:00",
                pnl_usd=pnl,
            ),
        )
    rows = ledger.load_rows(path)
    state = streak_state_from_ledger(rows, spec, _cfg())
    assert state.consecutive_wins == 1
    assert state.consecutive_losses == 0
    assert state.size_multiplier == 1.0
