"""Tests for Phase B cross-venue manual fills."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from world_cup_bot.cross_venue_config import CrossVenueConfig, DiscoveryConfig
from world_cup_bot.cross_venue_fills import (
    ManualFillInput,
    build_reconcile_report,
    compute_realized_pnl_usd,
    import_fills_csv,
    record_manual_fill,
)
from world_cup_bot.cross_venue_paper import PaperArbConfig, record_paper_arb_intents
from world_cup_bot.cross_venue_scanner import CrossVenueScanResult, CrossVenueScanRow
from world_cup_bot.ledger import load_rows


def _cfg() -> CrossVenueConfig:
    return CrossVenueConfig(
        version=1,
        alert_threshold_pp=5.0,
        alert_min_fee_adjusted_gap_pp=None,
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
        fee_adjusted_gap_pp=1.1,
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


def test_compute_realized_pnl_sell_buy():
    pnl = compute_realized_pnl_usd("SELL", "BUY", 0.68, 0.64, 500, fees_usd=2.0)
    assert pnl == pytest.approx(18.0)


def test_record_manual_fill_and_reconcile(tmp_path: Path):
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
    record_paper_arb_intents(result, _cfg(), PaperArbConfig(), path=ledger)

    fill = ManualFillInput(
        team="USA",
        market_type="group_winner",
        pm_fill_price=0.68,
        kalshi_fill_price=0.64,
        notional_usd=500,
        fees_usd=2.0,
    )
    rec = record_manual_fill(ledger, fill)
    assert rec.realized_pnl_usd == pytest.approx(18.0)

    report = build_reconcile_report(load_rows(ledger))
    assert report.matched == 1
    assert report.intent_only == 0
    assert report.rows[0].status == "matched"
    assert report.rows[0].delta_usd == pytest.approx(
        rec.realized_pnl_usd - report.rows[0].entry_profit_usd,
        abs=0.01,
    )


def test_import_fills_csv(tmp_path: Path):
    ledger = tmp_path / "cv.jsonl"
    csv_path = tmp_path / "fills.csv"
    csv_path.write_text(
        "timestamp,team,market_type,pm_leg,kalshi_leg,pm_price,kalshi_price,"
        "notional_usd,fees_usd,order_id_pm,order_id_kalshi,notes\n"
        "2026-05-30T12:00:00Z,USA,group_winner,SELL,BUY,0.68,0.64,500,1.0,,,\n",
        encoding="utf-8",
    )
    result = import_fills_csv(ledger, csv_path)
    assert result.imported == 1
    assert result.errors == ()
    rows = load_rows(ledger)
    assert len(rows) == 1
    assert rows[0]["event"] == "cross_venue_arb_fill_manual"


def test_reconcile_intent_only(tmp_path: Path):
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
    record_paper_arb_intents(result, _cfg(), PaperArbConfig(), path=ledger)
    report = build_reconcile_report(load_rows(ledger))
    assert report.intent_only == 1
    assert report.matched == 0
