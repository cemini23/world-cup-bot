"""Tests for ledger-persisted trading halts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.order_manager import TradingHalt
from world_cup_bot.trading_halt_persist import (
    record_trading_halt,
    record_trading_halt_clear,
    trading_halt_from_ledger,
)


def _spec() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        strategy_key="pm_wc_advance_lp",
        version_id="wc_advance_lp_v5",
        deployed_at=datetime.now(UTC),
        note="",
        legacy_version_ids=frozenset(),
    )


def test_trading_halt_from_ledger_team_and_global(tmp_path):
    path = tmp_path / "l.jsonl"
    spec = _spec()
    record_trading_halt(path, spec, team="Turkey", reason="fill kill-switch")
    halt = trading_halt_from_ledger(path)
    assert halt.is_halted("Turkey")
    assert not halt.global_halt
    assert "kill-switch" in halt.reason

    record_trading_halt_clear(path, spec, team="Turkey", reason="operator clear")
    halt = trading_halt_from_ledger(path)
    assert not halt.is_halted("Turkey")


def test_trading_halt_global_persists(tmp_path):
    path = tmp_path / "l.jsonl"
    spec = _spec()
    record_trading_halt(path, spec, reason="risk halt", global_halt=True)
    halt = trading_halt_from_ledger(path)
    assert halt.global_halt
    assert halt.is_halted("AnyTeam")

    record_trading_halt_clear(path, spec, global_clear=True)
    halt = trading_halt_from_ledger(path)
    assert not halt.global_halt


def test_trading_halt_empty_ledger():
    halt = trading_halt_from_ledger(Path("/nonexistent"))
    assert isinstance(halt, TradingHalt)
    assert not halt.global_halt
