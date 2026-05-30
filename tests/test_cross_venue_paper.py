"""Tests for Phase A cross-venue paper arb ledger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from world_cup_bot.cross_venue_config import CrossVenueConfig, DiscoveryConfig
from world_cup_bot.cross_venue_paper import (
    EVENT_INTENT,
    PaperArbConfig,
    fee_adjusted_gap_pp,
    proposal_from_alert_row,
    record_paper_arb_intents,
    summarize_paper_arb_pnl,
)
from world_cup_bot.cross_venue_scanner import CrossVenueScanResult, CrossVenueScanRow
from world_cup_bot.ledger import load_rows


def _cfg() -> CrossVenueConfig:
    return CrossVenueConfig(
        version=1,
        alert_threshold_pp=5.0,
        poll_interval_sec=120,
        fee_kalshi_profit_pct=7.0,
        verification_max_age_days=14,
        pairs=(),
        blockers=(),
        discovery=DiscoveryConfig(
            kalshi_ticker_prefixes=("KXWCGROUPWIN",),
            polymarket_search_queries=("world cup",),
            rules_hash_by_market_type={"group_winner": "hash_v1"},
            blocked_market_types=frozenset(),
        ),
    )


def _alert_row() -> CrossVenueScanRow:
    return CrossVenueScanRow(
        team="USA",
        market_type="group_winner",
        rules_hash="hash_v1",
        gap_pp=6.0,
        pm_mid=0.70,
        kalshi_mid=0.64,
        alert=True,
        pm_slug="usa-group-d",
        pm_question="Will USA win Group D?",
        kalshi_ticker="KXWCGROUPWIN-26D-USA",
        kalshi_title="USA wins group",
        kalshi_volume_24h=1000.0,
        slug_changed=False,
        slug_change_detail=None,
        blocked=False,
        block_reason=None,
        notes=None,
        source="config",
    )


def test_fee_adjusted_gap_pp():
    assert fee_adjusted_gap_pp(6.0, 7.0) == pytest.approx(5.58)


def test_proposal_from_alert_row():
    paper = PaperArbConfig(default_notional_usd=500)
    p = proposal_from_alert_row(_alert_row(), _cfg(), paper)
    assert p is not None
    assert p.pm_leg == "SELL"
    assert p.kalshi_leg == "BUY"
    assert p.theoretical_profit_usd == pytest.approx(27.90, rel=0.01)


def test_record_and_dedup(tmp_path: Path):
    paper = PaperArbConfig(default_notional_usd=500, dedup_interval_sec=3600)
    ledger = tmp_path / "cv.jsonl"
    result = CrossVenueScanResult(
        scanned_at=datetime.now(UTC).isoformat(),
        config_version=1,
        alert_threshold_pp=5.0,
        blockers=(),
        rows=(_alert_row(),),
        discoveries=(),
        pm_market_count=1,
        kalshi_market_count=1,
    )
    now = datetime.now(UTC)

    r1 = record_paper_arb_intents(
        result,
        _cfg(),
        paper,
        path=ledger,
        now=now,
    )
    assert r1.recorded == 1
    rows = load_rows(ledger)
    assert len(rows) == 1
    assert rows[0]["event"] == EVENT_INTENT

    r2 = record_paper_arb_intents(
        result,
        _cfg(),
        paper,
        path=ledger,
        now=now + timedelta(minutes=5),
    )
    assert r2.recorded == 0
    assert r2.skipped_dedup == 1


def test_summarize_paper_arb_pnl_with_refresh(tmp_path: Path):
    paper = PaperArbConfig()
    ledger = tmp_path / "cv.jsonl"
    result = CrossVenueScanResult(
        scanned_at=datetime.now(UTC).isoformat(),
        config_version=1,
        alert_threshold_pp=5.0,
        blockers=(),
        rows=(_alert_row(),),
        discoveries=(),
        pm_market_count=1,
        kalshi_market_count=1,
    )
    record_paper_arb_intents(result, _cfg(), paper, path=ledger)

    converged_row = CrossVenueScanRow(
        team="USA",
        market_type="group_winner",
        rules_hash="hash_v1",
        gap_pp=2.0,
        pm_mid=0.66,
        kalshi_mid=0.64,
        alert=False,
        pm_slug="usa-group-d",
        pm_question="q",
        kalshi_ticker="KXWCGROUPWIN-26D-USA",
        kalshi_title="t",
        kalshi_volume_24h=None,
        slug_changed=False,
        slug_change_detail=None,
        blocked=False,
        block_reason=None,
        notes=None,
        source="config",
    )
    refresh = CrossVenueScanResult(
        scanned_at=datetime.now(UTC).isoformat(),
        config_version=1,
        alert_threshold_pp=5.0,
        blockers=(),
        rows=(converged_row,),
        discoveries=(),
        pm_market_count=1,
        kalshi_market_count=1,
    )

    summary = summarize_paper_arb_pnl(load_rows(ledger), _cfg(), paper, scan=refresh)
    assert summary.intent_count == 1
    assert summary.converged_count == 1
    assert summary.positions[0].status == "converged"
