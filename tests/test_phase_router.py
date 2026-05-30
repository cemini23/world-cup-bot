"""Tests for Module 1b phase router."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from world_cup_bot import phase_router
from world_cup_bot.market_phases import load_market_phases_config


@pytest.fixture
def config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "market_phases.yaml"


def test_load_market_phases_has_fsm(config_path: Path):
    cfg = load_market_phases_config(config_path)
    assert cfg.version >= 2
    assert "group_stage" in cfg.tournament_states
    assert "round_of_32" in cfg.tournament_states
    assert cfg.phases["group_advance"].status == "active"


def test_auto_detect_pre_tournament(config_path: Path):
    ctx = phase_router.resolve_phase_router(
        config_path,
        now=datetime(2026, 5, 30, 12, 0, tzinfo=UTC),
        enabled=True,
    )
    assert ctx.tournament_phase == "pre_tournament"
    assert ctx.source == "auto"
    assert "group_advance" in ctx.lp_active_phases


def test_env_override(config_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WC_TOURNAMENT_PHASE", "quarterfinal")
    ctx = phase_router.resolve_phase_router(
        config_path,
        now=datetime(2026, 5, 30, tzinfo=UTC),
        enabled=True,
    )
    assert ctx.tournament_phase == "quarterfinal"
    assert ctx.source == "env"
    assert ctx.forced is True
    assert ctx.operating_overrides.get("cancel_hours") == 24


def test_forced_state_file(config_path: Path, tmp_path: Path):
    ovr = tmp_path / "override.json"
    phase_router.write_forced_state(ovr, "round_of_16")
    ctx = phase_router.resolve_phase_router(
        config_path,
        now=datetime(2026, 5, 30, tzinfo=UTC),
        enabled=True,
        override_path=ovr,
    )
    assert ctx.tournament_phase == "round_of_16"
    assert ctx.source == "override_file"


def test_router_disabled(config_path: Path):
    ctx = phase_router.resolve_phase_router(config_path, enabled=False)
    assert ctx.tournament_phase == "disabled"
    assert phase_router.lp_quoting_allowed(ctx) is True


def test_lp_gate_knockout_without_group(config_path: Path):
    ctx = phase_router.resolve_phase_router(
        config_path,
        now=datetime(2026, 7, 10, tzinfo=UTC),
        enabled=True,
    )
    assert ctx.tournament_phase == "quarterfinal"
    assert phase_router.lp_quoting_allowed(ctx, market_phase_id="group_advance") is False
    assert phase_router.lp_quoting_allowed(ctx, market_phase_id="reach_semifinal") is True


def test_settlement_gate_holds_knockout_transition(config_path: Path):
    from world_cup_bot.settlement_gate import PhaseSettlementStatus, SettlementGateReport

    report = SettlementGateReport(
        by_phase={
            "group_advance": PhaseSettlementStatus("group_advance", 48, 10),
        },
        pending_phase_ids=("group_advance",),
    )
    ctx = phase_router.resolve_phase_router(
        config_path,
        now=datetime(2026, 7, 1, tzinfo=UTC),
        enabled=True,
        settlement_gate_enabled=True,
        settlement_report=report,
    )
    assert ctx.calendar_phase == "round_of_32"
    assert ctx.tournament_phase == "group_to_knockout_transition"
    assert ctx.source == "settlement_gate"
    assert ctx.settlement_blocked_by == "group_advance"


def test_effective_cancel_hours(config_path: Path):
    ctx = phase_router.resolve_phase_router(
        config_path,
        now=datetime(2026, 7, 10, tzinfo=UTC),
        enabled=True,
    )
    assert phase_router.effective_cancel_hours(ctx, 10.0) == 24.0
