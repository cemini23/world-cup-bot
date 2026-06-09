"""Tests for round-trip fill economics."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from world_cup_bot import ledger
from world_cup_bot.fill_economics import (
    attribute_roundtrip_from_exit_intent,
    backfill_position_exits,
    compute_exit_pnl_usd,
    position_exit_exists,
)
from world_cup_bot.fill_handler import ExitIntent
from world_cup_bot.logic_version import PnlScope, StrategyVersionSpec


def _spec() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        strategy_key="pm_wc_advance_lp",
        version_id="wc_advance_lp_v5",
        deployed_at=datetime.now(UTC),
        note="",
        legacy_version_ids=frozenset(),
    )


def _exit_intent(**overrides) -> ExitIntent:
    base = dict(
        team="Turkey",
        side="YES",
        token_id="tok-yes",
        order_id="exit-1",
        price=0.52,
        size_shares=100.0,
        due_by=datetime.now(UTC),
        reason="test",
        kill_switch=False,
    )
    base.update(overrides)
    return ExitIntent(**base)


def test_compute_exit_pnl_usd():
    assert compute_exit_pnl_usd(
        entry_price=0.44, exit_price=0.52, size_shares=100
    ) == pytest.approx(8.0)


def test_attribute_roundtrip_writes_position_exit(tmp_path):
    path = tmp_path / "l.jsonl"
    spec = _spec()
    ledger.record_fill(
        path=path,
        spec=spec,
        team="Turkey",
        side="YES",
        order_id="entry-1",
        price=0.44,
        size_shares=100.0,
        pnl_usd=0.0,
    )
    pnl = attribute_roundtrip_from_exit_intent(
        path=path,
        spec=spec,
        exit_intent=_exit_intent(price=0.52, size_shares=100.0),
        fill_order_id="entry-1",
        entry_price=0.44,
        dry_run=False,
    )
    assert pnl == pytest.approx(8.0)
    rows = ledger.load_rows(path)
    assert position_exit_exists(rows, "entry-1")
    summary = ledger.summarize_pnl(rows, spec, PnlScope.CURRENT)
    assert summary.realized_pnl_usd == pytest.approx(8.0)


def test_attribute_roundtrip_idempotent(tmp_path):
    path = tmp_path / "l.jsonl"
    spec = _spec()
    ledger.record_fill(
        path=path,
        spec=spec,
        team="Turkey",
        side="YES",
        order_id="entry-1",
        price=0.44,
        size_shares=100.0,
        pnl_usd=0.0,
    )
    intent = _exit_intent(price=0.52, size_shares=100.0)
    kw = dict(
        path=path,
        spec=spec,
        exit_intent=intent,
        fill_order_id="entry-1",
        entry_price=0.44,
        dry_run=False,
    )
    assert attribute_roundtrip_from_exit_intent(**kw) == pytest.approx(8.0)
    assert attribute_roundtrip_from_exit_intent(**kw) is None
    assert len([r for r in ledger.load_rows(path) if r.get("event") == "position_exit"]) == 1


def test_backfill_position_exits_from_historical_rows(tmp_path):
    path = tmp_path / "l.jsonl"
    spec = _spec()
    ts = datetime.now(UTC).isoformat()
    ledger.append_row(
        path,
        ledger.LedgerRow(
            event="order_fill",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=ts,
            team="Turkey",
            side="YES",
            order_id="entry-hist",
            price=0.40,
            size_shares=50.0,
            pnl_usd=0.0,
        ),
    )
    ledger.append_row(
        path,
        ledger.LedgerRow(
            event="exit_intent",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=ts,
            team="Turkey",
            side="YES",
            order_id="exit-hist",
            price=0.46,
            size_shares=50.0,
            extra={
                "fill_order_id": "entry-hist",
                "token_id": "tok",
                "due_by": ts,
                "kill_switch": False,
            },
        ),
    )
    written = backfill_position_exits(path, spec)
    assert written == 1
    rows = ledger.load_rows(path)
    assert position_exit_exists(rows, "entry-hist")
    summary = ledger.summarize_pnl(rows, spec, PnlScope.CURRENT)
    assert summary.realized_pnl_usd == pytest.approx(3.0)


def test_synthesize_position_exits_for_orphan_fills(tmp_path):
    from world_cup_bot.operating_config import load_operating_config

    path = tmp_path / "l.jsonl"
    spec = _spec()
    ts = datetime.now(UTC).isoformat()
    ledger.append_row(
        path,
        ledger.LedgerRow(
            event="order_fill",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=ts,
            team="Turkey",
            side="YES",
            order_id="orphan-entry",
            price=0.50,
            size_shares=100.0,
        ),
    )
    operating = load_operating_config()
    from world_cup_bot.fill_economics import synthesize_position_exits_from_entry_fills

    written = synthesize_position_exits_from_entry_fills(path, spec, operating)
    assert written == 1
    rows = ledger.load_rows(path)
    ticks = operating.fill_handler.exit_loss_ticks
    exit_row = next(r for r in rows if r.get("event") == "position_exit")
    assert exit_row.get("reason") == "backfill_synthetic_exit"
    assert float(exit_row["pnl_usd"]) == pytest.approx(-0.01 * ticks * 100.0)
    summary = ledger.summarize_pnl(rows, spec, PnlScope.CURRENT)
    assert summary.realized_pnl_usd == 0.0
