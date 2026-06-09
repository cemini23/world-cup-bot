"""Persist trading halts in the ledger across plan/watch processes."""

from __future__ import annotations

from pathlib import Path

from world_cup_bot.ledger import LedgerRow, append_row, load_rows
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.order_manager import TradingHalt


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def record_trading_halt(
    path: Path,
    spec: StrategyVersionSpec,
    *,
    team: str | None = None,
    reason: str,
    global_halt: bool = False,
) -> None:
    append_row(
        path,
        LedgerRow(
            event="trading_halt",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=_now_iso(),
            team=team,
            reason=reason,
            extra={"global": global_halt},
        ),
    )


def record_trading_halt_clear(
    path: Path,
    spec: StrategyVersionSpec,
    *,
    team: str | None = None,
    global_clear: bool = False,
    reason: str = "operator clear",
) -> None:
    append_row(
        path,
        LedgerRow(
            event="trading_halt_clear",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=_now_iso(),
            team=team,
            reason=reason,
            extra={"global": global_clear},
        ),
    )


def trading_halt_from_ledger(path: Path) -> TradingHalt:
    """Rebuild halt state from ledger events (newest wins per team/global)."""
    halt = TradingHalt()
    if not path.is_file():
        return halt
    rows = load_rows(path)
    team_state: dict[str, bool] = {}
    global_state = False
    last_reason = ""
    for row in rows:
        ev = row.get("event")
        extra = row.get("extra") or {}
        team = row.get("team")
        is_global = bool(row.get("global") or extra.get("global"))
        if ev == "trading_halt_clear":
            if is_global or team is None:
                global_state = False
            if team:
                team_state[str(team)] = False
        elif ev == "trading_halt":
            last_reason = str(row.get("reason") or last_reason)
            if is_global:
                global_state = True
            if team:
                team_state[str(team)] = True
        elif ev == "risk_permanent_halt":
            global_state = True
            last_reason = str(row.get("reason") or last_reason)

    halt.global_halt = global_state
    halt.halted_teams = {t for t, active in team_state.items() if active}
    halt.reason = last_reason
    return halt
