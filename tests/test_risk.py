"""Tests for daily adverse-fill risk gate."""

from datetime import UTC, datetime
from pathlib import Path

from world_cup_bot import ledger
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.operating_config import OperatingConfig, RiskOps
from world_cup_bot.risk import check_daily_adverse_budget, daily_adverse_fill_usd


def _spec() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        strategy_key="pm_wc_advance_lp",
        version_id="wc_advance_lp_v4",
        deployed_at=datetime.now(UTC),
        note="",
        legacy_version_ids=frozenset(),
    )


def _operating(cap: float = 500) -> OperatingConfig:
    from world_cup_bot.operating_config import (
        BilateralOps,
        CalendarOps,
        FillHandlerOps,
        LiquidityOps,
        PromotionOps,
    )

    return OperatingConfig(
        calendar=CalendarOps(prefer_hours_before_kickoff=24),
        bilateral=BilateralOps(high_mid=0.90, low_mid=0.10),
        fill_handler=FillHandlerOps(
            exit_within_seconds=60,
            queue_depletion_usd=150,
            vol_drop_pct=0.25,
            vol_cooldown_minutes=30,
            exit_loss_ticks=1,
        ),
        liquidity=LiquidityOps(
            min_depth_within_reward_spread_usd=50,
            min_ask_depth_within_reward_spread_usd=15,
            min_combined_book_depth_usd=150,
            min_levels_per_side=2,
            max_spread_cents=None,
            auto_clear_human_review=True,
        ),
        risk=RiskOps(max_daily_adverse_fill_usd=cap),
        promotion=PromotionOps(
            min_fills=5,
            min_distinct_days=3,
            min_dsr=0.0,
            max_mcpt_p=0.10,
        ),
    )


def test_daily_adverse_fill_sums_negative_pnl(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    spec = _spec()
    ledger.append_row(
        path,
        ledger.LedgerRow(
            event="order_fill",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp="2026-05-29T12:00:00+00:00",
            pnl_usd=-120.0,
        ),
    )
    ledger.append_row(
        path,
        ledger.LedgerRow(
            event="order_fill",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp="2026-05-29T13:00:00+00:00",
            pnl_usd=-80.0,
        ),
    )
    rows = ledger.load_rows(path)
    assert daily_adverse_fill_usd(rows, day="2026-05-29", spec=spec) == 200.0


def test_daily_adverse_fill_uses_notional_when_pnl_missing(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    spec = _spec()
    ledger.append_row(
        path,
        ledger.LedgerRow(
            event="order_fill",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp="2026-05-29T12:00:00+00:00",
            price=0.50,
            size_shares=200.0,
            notional_usd=100.0,
        ),
    )
    rows = ledger.load_rows(path)
    assert daily_adverse_fill_usd(rows, day="2026-05-29", spec=spec) == 100.0


def test_daily_adverse_budget_blocks_at_cap(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    spec = _spec()
    ledger.append_row(
        path,
        ledger.LedgerRow(
            event="order_fill",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp="2026-05-29T12:00:00+00:00",
            pnl_usd=-600.0,
        ),
    )
    ok, detail = check_daily_adverse_budget(path, _operating(500), spec, day="2026-05-29")
    assert ok is False
    assert "600" in detail
