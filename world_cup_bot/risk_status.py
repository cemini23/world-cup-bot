"""Risk gates status payload — streak sizing + portfolio gates (K102)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from world_cup_bot.config import Settings
from world_cup_bot.ledger import load_rows
from world_cup_bot.logic_version import load_strategy_version
from world_cup_bot.portfolio_gates import (
    bankroll_usd_from_env,
    check_portfolio_gates,
    portfolio_status,
)
from world_cup_bot.risk_gates_config import load_risk_gates_config
from world_cup_bot.streak_sizing import streak_state_from_ledger


def build_risk_status_payload(settings: Settings) -> dict[str, Any]:
    rg_cfg = load_risk_gates_config()
    spec = load_strategy_version(Path(settings.logic_version_config))
    ledger_path = Path(settings.ledger_path)
    rows = load_rows(ledger_path) if ledger_path.is_file() else []

    streak = streak_state_from_ledger(rows, spec, rg_cfg.dynamic_sizing)
    pg = portfolio_status(ledger_path, spec, rg_cfg)
    gate = check_portfolio_gates(ledger_path, spec, rg_cfg, record_breach=False)

    return {
        "logic_version": rg_cfg.logic_version,
        "dynamic_sizing": {
            "enabled": rg_cfg.dynamic_sizing.enabled,
            "consecutive_wins": streak.consecutive_wins,
            "consecutive_losses": streak.consecutive_losses,
            "size_multiplier": streak.size_multiplier,
            "fill_outcomes_count": streak.fill_outcomes_count,
            "config": {
                "loss_reduction_pct": rg_cfg.dynamic_sizing.loss_reduction_pct,
                "loss_streak_threshold": rg_cfg.dynamic_sizing.loss_streak_threshold,
                "win_increase_pct": rg_cfg.dynamic_sizing.win_increase_pct,
                "win_streak_threshold": rg_cfg.dynamic_sizing.win_streak_threshold,
                "win_streak_cap": rg_cfg.dynamic_sizing.win_streak_cap,
                "min_size_multiplier": rg_cfg.dynamic_sizing.min_size_multiplier,
                "max_size_multiplier": rg_cfg.dynamic_sizing.max_size_multiplier,
            },
        },
        "portfolio_gates": {
            "enabled": rg_cfg.portfolio_gates.enabled,
            "bankroll_usd": pg.bankroll_usd,
            "wc_bankroll_env_set": bankroll_usd_from_env() is not None,
            "cumulative_net_pnl_usd": pg.cumulative_net_pnl_usd,
            "peak_equity_usd": pg.peak_equity_usd,
            "drawdown_pct": pg.drawdown_pct,
            "daily_loss_usd": pg.daily_loss_usd,
            "monthly_loss_usd": pg.monthly_loss_usd,
            "permanent_halt": pg.permanent_halt,
            "plan_allowed": gate.allowed,
            "plan_detail": gate.reason,
            "active_gate": gate.gate,
            "paused_until": gate.paused_until.isoformat() if gate.paused_until else None,
        },
    }
