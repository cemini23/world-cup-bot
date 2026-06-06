"""Tests for K102 portfolio PnL gates."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from world_cup_bot import ledger
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.portfolio_gates import (
    active_gate_pause,
    check_portfolio_gates,
    record_gate_breach,
)
from world_cup_bot.risk_gates_config import (
    PortfolioGatesConfig,
    RiskGatesConfig,
    load_risk_gates_config,
)


def _spec() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        strategy_key="pm_wc_advance_lp",
        version_id="wc_advance_lp_v5",
        deployed_at=datetime.now(UTC),
        note="",
        legacy_version_ids=frozenset(),
    )


def _rg_cfg(*, portfolio_enabled: bool = True) -> RiskGatesConfig:
    base = load_risk_gates_config()
    pg = base.portfolio_gates
    return RiskGatesConfig(
        version=base.version,
        logic_version=base.logic_version,
        dynamic_sizing=base.dynamic_sizing,
        portfolio_gates=PortfolioGatesConfig(
            enabled=portfolio_enabled,
            daily_loss_pct=pg.daily_loss_pct,
            daily_pause_minutes=pg.daily_pause_minutes,
            monthly_loss_pct=pg.monthly_loss_pct,
            monthly_pause_days=pg.monthly_pause_days,
            peak_drawdown_pct=pg.peak_drawdown_pct,
            peak_pause_days=pg.peak_pause_days,
            total_loss_pct=pg.total_loss_pct,
        ),
    )


def test_portfolio_gates_disabled():
    path = pytest.importorskip("pathlib").Path("/nonexistent")
    result = check_portfolio_gates(path, _spec(), _rg_cfg(portfolio_enabled=False))
    assert result.allowed


def test_portfolio_gates_deferred_in_dry_run(tmp_path, monkeypatch):
    from world_cup_bot.config import Settings

    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("WC_BANKROLL_USD", raising=False)
    monkeypatch.setenv("WC_BANKROLL_FROM_WALLET", "0")
    settings = Settings.from_env()
    result = check_portfolio_gates(tmp_path / "l.jsonl", _spec(), _rg_cfg(), settings=settings)
    assert result.allowed
    assert "DRY_RUN" in result.reason


def test_portfolio_gates_requires_bankroll(tmp_path, monkeypatch):
    from world_cup_bot.config import Settings

    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.delenv("WC_BANKROLL_USD", raising=False)
    monkeypatch.setenv("WC_BANKROLL_FROM_WALLET", "0")
    path = tmp_path / "l.jsonl"
    settings = Settings.from_env()
    result = check_portfolio_gates(path, _spec(), _rg_cfg(), settings=settings)
    assert not result.allowed
    assert "bankroll unavailable" in result.reason


def test_daily_loss_triggers_pause(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_BANKROLL_USD", "1000")
    path = tmp_path / "l.jsonl"
    spec = _spec()
    ledger.append_row(
        path,
        ledger.LedgerRow(
            event="order_fill",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=datetime.now(UTC).isoformat(),
            pnl_usd=-60.0,
        ),
    )
    result = check_portfolio_gates(path, spec, _rg_cfg(), record_breach=True)
    assert not result.allowed
    assert result.gate == "daily_loss"
    rows = ledger.load_rows(path)
    assert any(r.get("event") == "risk_gate_breach" for r in rows)


def test_active_pause_blocks_until_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv("WC_BANKROLL_USD", "1000")
    path = tmp_path / "l.jsonl"
    rg = _rg_cfg()
    until = datetime.now(UTC) + timedelta(minutes=30)
    record_gate_breach(
        path,
        rg,
        gate="daily_loss",
        reason="test pause",
        paused_until=until,
    )
    rows = ledger.load_rows(path)
    pause = active_gate_pause(rows, rg)
    assert pause is not None
    assert not pause.allowed


def test_permanent_halt_idempotent(tmp_path):
    path = tmp_path / "l.jsonl"
    rg = _rg_cfg()
    record_gate_breach(path, rg, gate="total_loss", reason="halt", permanent=True)
    record_gate_breach(path, rg, gate="total_loss", reason="halt again", permanent=True)
    rows = ledger.load_rows(path)
    halts = [r for r in rows if r.get("event") == "risk_permanent_halt"]
    assert len(halts) == 2
    pause = active_gate_pause(rows, rg)
    assert pause is not None
    assert pause.permanent_halt
