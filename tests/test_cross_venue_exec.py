"""Tests for Phase C cross-venue auto execution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from world_cup_bot.cross_venue_config import CrossVenueConfig, DiscoveryConfig
from world_cup_bot.cross_venue_exec import (
    EVENT_EXEC_START,
    EXEC_SPEC,
    AutoArbConfig,
    DualLegPlan,
    ExecAttemptResult,
    _recent_exec_intent_keys,
    auto_exec_on_alerts,
    check_exec_caps,
    check_exec_gates,
    cross_venue_exec_ack,
    execute_dual_leg,
    list_orphans,
)
from world_cup_bot.cross_venue_scanner import CrossVenueScanRow
from world_cup_bot.kalshi_orders import KalshiOrderRequest, KalshiOrderResult, build_kalshi_order
from world_cup_bot.ledger import LedgerRow, append_row, load_rows


class _FakePmClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def post_arb_order(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("pm post failed")
        return {"orderID": "pm-123", "status": "submitted"}


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


def _plan() -> DualLegPlan:
    return DualLegPlan(
        team="USA",
        market_type="group_winner",
        intent_key="group_winner:USA",
        notional_usd=100.0,
        pm_leg="SELL",
        kalshi_leg="BUY",
        pm_price=0.68,
        kalshi_price=0.64,
        pm_token_id="yes-tok",
        pm_condition_id="0xabc",
        kalshi_ticker="KXWCGROUPWIN-26D-USA",
        correlation_id="test-corr-1",
        fee_adjusted_gap_pp=5.5,
    )


def test_build_kalshi_order_buy():
    req = build_kalshi_order(
        ticker="KXWCGROUPWIN-26D-USA",
        leg="BUY",
        price=0.64,
        notional_usd=100,
    )
    assert req.action == "buy"
    assert req.side == "yes"
    assert req.count >= 1
    assert req.yes_price_cents == 64


def test_check_exec_caps_blocks_daily(tmp_path: Path):
    ledger = tmp_path / "l.jsonl"
    from world_cup_bot.cross_venue_exec import EVENT_EXEC_COMPLETE, EXEC_SPEC
    from world_cup_bot.ledger import LedgerRow, append_row

    append_row(
        ledger,
        LedgerRow(
            event=EVENT_EXEC_COMPLETE,
            logic_version=EXEC_SPEC.version_id,
            strategy_key=EXEC_SPEC.strategy_key,
            timestamp=datetime.now(UTC).isoformat(),
            notional_usd=450,
            correlation_id="cap-test-1",
        ),
    )
    auto = AutoArbConfig(max_daily_notional_usd=500, max_notional_usd=100)
    ok, msg = check_exec_caps(load_rows(ledger), auto, notional_usd=100)
    assert not ok
    assert "daily cap" in msg


def test_check_exec_caps_ignores_exec_leg_rows(tmp_path: Path):
    """Leg rows must not inflate daily notional — only completion rows count."""
    ledger = tmp_path / "l.jsonl"
    from world_cup_bot.cross_venue_exec import EVENT_EXEC_COMPLETE, EVENT_EXEC_LEG, EXEC_SPEC
    from world_cup_bot.ledger import LedgerRow, append_row

    ts = datetime.now(UTC).isoformat()
    cid = "cap-test-2"
    for notional in (200, 200):
        append_row(
            ledger,
            LedgerRow(
                event=EVENT_EXEC_LEG,
                logic_version=EXEC_SPEC.version_id,
                strategy_key=EXEC_SPEC.strategy_key,
                timestamp=ts,
                notional_usd=notional,
                correlation_id=cid,
            ),
        )
    append_row(
        ledger,
        LedgerRow(
            event=EVENT_EXEC_COMPLETE,
            logic_version=EXEC_SPEC.version_id,
            strategy_key=EXEC_SPEC.strategy_key,
            timestamp=ts,
            notional_usd=200,
            correlation_id=cid,
        ),
    )
    auto = AutoArbConfig(max_daily_notional_usd=500, max_notional_usd=100)
    ok, msg = check_exec_caps(load_rows(ledger), auto, notional_usd=100)
    assert ok, msg


def test_execute_dual_leg_dry_run(tmp_path: Path):
    ledger = tmp_path / "l.jsonl"
    pm = _FakePmClient()

    def _kal_place(req: KalshiOrderRequest, *, dry_run: bool = False) -> KalshiOrderResult:
        return KalshiOrderResult(
            order_id="kal-1",
            ticker=req.ticker,
            status="submitted",
            dry_run=dry_run,
            raw={},
        )

    result = execute_dual_leg(
        _plan(),
        ledger_path=ledger,
        kalshi_auth=None,
        kalshi_base_url="https://example.com/trade-api/v2",
        pm_client=pm,
        dry_run=True,
        kalshi_place=_kal_place,
    )
    assert result.status == "dry_run"
    assert result.pm_leg is not None
    assert result.kalshi_leg is not None
    assert result.realized_pnl_usd is None
    assert len(pm.calls) == 1
    rows = load_rows(ledger)
    complete = [r for r in rows if r["event"] == "cross_venue_arb_exec_complete"]
    assert len(complete) == 1
    assert complete[0].get("pnl_usd") is None
    assert complete[0].get("leg_status") == "dry_run"
    assert not any(r["event"] == "cross_venue_arb_fill_manual" for r in rows)


def test_execute_orphan_on_pm_failure(tmp_path: Path):
    ledger = tmp_path / "l.jsonl"
    pm = _FakePmClient(fail=True)
    cancelled: list[str] = []

    def _kal_place(req: KalshiOrderRequest, *, dry_run: bool = False) -> KalshiOrderResult:
        return KalshiOrderResult(
            order_id="kal-orphan",
            ticker=req.ticker,
            status="submitted",
            dry_run=False,
            raw={},
        )

    def _kal_cancel(order_id: str, *, dry_run: bool = False) -> dict:
        cancelled.append(order_id)
        return {"status": "cancelled"}

    result = execute_dual_leg(
        _plan(),
        ledger_path=ledger,
        kalshi_auth=None,
        kalshi_base_url="https://example.com/trade-api/v2",
        pm_client=pm,
        dry_run=False,
        kalshi_place=_kal_place,
        kalshi_cancel=_kal_cancel,
    )
    assert result.status == "orphan"
    assert result.orphan_venue == "kalshi"
    assert cancelled == ["kal-orphan"]
    orphans = list_orphans(load_rows(ledger))
    assert len(orphans) == 1


def _alert_row(*, team: str = "USA", gap: float = 6.0) -> CrossVenueScanRow:
    return CrossVenueScanRow(
        team=team,
        market_type="group_winner",
        rules_hash="hash_v1",
        gap_pp=gap,
        fee_adjusted_gap_pp=1.24,
        pm_mid=0.68,
        kalshi_mid=0.62,
        alert=True,
        pm_slug="will-usa-win-group-d",
        pm_question="USA group D?",
        kalshi_ticker="KXWCGROUPWIN-26D-USA",
        kalshi_title="USA group winner",
        kalshi_volume_24h=1000.0,
        slug_changed=False,
        slug_change_detail=None,
        blocked=False,
        block_reason=None,
        notes=None,
        source="config",
    )


def test_cross_venue_exec_ack_env(monkeypatch):
    monkeypatch.delenv("WC_CROSS_VENUE_EXEC_ACK", raising=False)
    assert not cross_venue_exec_ack()
    monkeypatch.setenv("WC_CROSS_VENUE_EXEC_ACK", "1")
    assert cross_venue_exec_ack()


def test_check_exec_gates_blocks_without_auto_exec(monkeypatch):
    monkeypatch.delenv("WC_CROSS_VENUE_AUTO_EXEC", raising=False)
    gate = check_exec_gates(dry_run=False, force=False)
    assert not gate.allowed
    assert "AUTO_EXEC" in gate.reason


def test_check_exec_gates_force_allows_dry_sim(monkeypatch):
    monkeypatch.delenv("WC_CROSS_VENUE_AUTO_EXEC", raising=False)
    gate = check_exec_gates(dry_run=True, force=True)
    assert gate.allowed
    assert gate.dry_run


def test_check_exec_gates_live_requires_ack(monkeypatch):
    monkeypatch.setenv("WC_CROSS_VENUE_AUTO_EXEC", "1")
    monkeypatch.delenv("WC_CROSS_VENUE_EXEC_ACK", raising=False)
    gate = check_exec_gates(dry_run=False, force=False)
    assert not gate.allowed
    assert "EXEC_ACK" in gate.reason


def test_recent_exec_intent_keys_dedup_window(tmp_path: Path):
    ledger = tmp_path / "l.jsonl"
    ts = datetime.now(UTC).isoformat()
    append_row(
        ledger,
        LedgerRow(
            event=EVENT_EXEC_START,
            logic_version=EXEC_SPEC.version_id,
            strategy_key=EXEC_SPEC.strategy_key,
            timestamp=ts,
            team="USA",
            extra={"intent_key": "group_winner:USA"},
        ),
    )
    keys = _recent_exec_intent_keys(load_rows(ledger), window_sec=3600.0)
    assert keys == {"group_winner:USA"}


def test_auto_exec_on_alerts_respects_auto_exec_flag(monkeypatch):
    monkeypatch.delenv("WC_CROSS_VENUE_AUTO_EXEC", raising=False)
    settings = SimpleNamespace(dry_run=True, gamma_url="https://gamma.example")
    out = auto_exec_on_alerts([_alert_row()], settings=settings, cfg=_cfg())
    assert out == []


def test_auto_exec_on_alerts_picks_best_gap(monkeypatch):
    monkeypatch.setenv("WC_CROSS_VENUE_AUTO_EXEC", "1")
    settings = SimpleNamespace(dry_run=True, gamma_url="https://gamma.example")

    def _fake_attempt(row, **kwargs):
        return ExecAttemptResult(
            team=row.team,
            market_type=row.market_type,
            status="dry_run",
            reason=None,
            dry_run=True,
            correlation_id=f"corr-{row.team}",
        )

    rows = [_alert_row(team="USA", gap=5.0), _alert_row(team="England", gap=8.0)]
    with patch("world_cup_bot.cross_venue_exec.attempt_exec_for_row", side_effect=_fake_attempt):
        out = auto_exec_on_alerts(rows, settings=settings, cfg=_cfg(), max_attempts=1)
    assert len(out) == 1
    assert out[0].team == "England"
