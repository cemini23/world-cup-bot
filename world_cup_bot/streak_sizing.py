"""Streak-based quote size multiplier (K102 / Polymarket-bot v3.1 math, Python-native)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from world_cup_bot.logic_version import PnlScope, StrategyVersionSpec, filter_rows_by_scope
from world_cup_bot.risk_gates_config import DynamicSizingConfig


@dataclass(frozen=True)
class StreakState:
    consecutive_wins: int
    consecutive_losses: int
    size_multiplier: float
    fill_outcomes_count: int


def _roundtrip_pnl(row: dict[str, Any]) -> float | None:
    """Realized round-trip PnL for streak sizing (position_exit rows only)."""
    if row.get("event") != "position_exit":
        return None
    from world_cup_bot.ledger import is_synthetic_backfill_exit

    if is_synthetic_backfill_exit(row):
        return None
    for key in ("pnl_usd", "realized_pnl_usd"):
        val = row.get(key)
        if val is not None:
            return float(val)
    return None


def _chronological_roundtrip_pnls(
    rows: list[dict[str, Any]],
    spec: StrategyVersionSpec,
) -> list[float]:
    scoped = filter_rows_by_scope(rows, spec, PnlScope.CURRENT)
    dated: list[tuple[str, float]] = []
    for row in scoped:
        pnl = _roundtrip_pnl(row)
        if pnl is None:
            continue
        ts = str(row.get("timestamp") or "")
        dated.append((ts, pnl))
    dated.sort(key=lambda x: x[0])
    return [p for _, p in dated]


def trailing_streaks(pnls: list[float]) -> tuple[int, int]:
    """Consecutive wins/losses at tail of outcome list (by signed pnl)."""
    if not pnls:
        return 0, 0
    last_win = pnls[-1] > 0
    wins = losses = 0
    for pnl in reversed(pnls):
        is_win = pnl > 0
        if is_win != last_win:
            break
        if is_win:
            wins += 1
        else:
            losses += 1
    return wins, losses


def dynamic_size_multiplier(
    cfg: DynamicSizingConfig,
    *,
    consecutive_wins: int,
    consecutive_losses: int,
) -> float:
    mult = 1.0
    if consecutive_losses > cfg.loss_streak_threshold:
        exp = consecutive_losses - cfg.loss_streak_threshold
        mult *= (1.0 - cfg.loss_reduction_pct) ** exp
    if consecutive_wins > cfg.win_streak_threshold:
        bonus_steps = min(
            consecutive_wins - cfg.win_streak_threshold,
            cfg.win_streak_cap,
        )
        mult *= 1.0 + bonus_steps * cfg.win_increase_pct
    return max(cfg.min_size_multiplier, min(cfg.max_size_multiplier, mult))


def streak_state_from_ledger(
    rows: list[dict[str, Any]],
    spec: StrategyVersionSpec,
    cfg: DynamicSizingConfig,
) -> StreakState:
    pnls = _chronological_roundtrip_pnls(rows, spec)
    wins, losses = trailing_streaks(pnls)
    mult = dynamic_size_multiplier(cfg, consecutive_wins=wins, consecutive_losses=losses)
    return StreakState(
        consecutive_wins=wins,
        consecutive_losses=losses,
        size_multiplier=round(mult, 4),
        fill_outcomes_count=len(pnls),
    )
