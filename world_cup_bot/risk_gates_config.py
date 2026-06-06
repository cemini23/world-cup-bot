"""Load config/risk_gates.yaml — streak sizing + portfolio gates (K102)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from world_cup_bot.paths import resolve_project_path

DEFAULT_RISK_GATES = resolve_project_path("config/risk_gates.yaml")


@dataclass(frozen=True)
class DynamicSizingConfig:
    enabled: bool
    loss_reduction_pct: float
    loss_streak_threshold: int
    win_increase_pct: float
    win_streak_threshold: int
    win_streak_cap: int
    min_size_multiplier: float
    max_size_multiplier: float


@dataclass(frozen=True)
class PortfolioGatesConfig:
    enabled: bool
    daily_loss_pct: float
    daily_pause_minutes: int
    monthly_loss_pct: float
    monthly_pause_days: int
    peak_drawdown_pct: float
    peak_pause_days: int
    total_loss_pct: float


@dataclass(frozen=True)
class RiskGatesConfig:
    version: int
    logic_version: str
    dynamic_sizing: DynamicSizingConfig
    portfolio_gates: PortfolioGatesConfig


def load_risk_gates_config(path: Path | str | None = None) -> RiskGatesConfig:
    cfg_path = Path(path) if path else DEFAULT_RISK_GATES
    raw = yaml.safe_load(cfg_path.read_text()) or {}
    ds = raw.get("dynamic_sizing") or {}
    pg = raw.get("portfolio_gates") or {}
    return RiskGatesConfig(
        version=int(raw.get("version", 1)),
        logic_version=str(raw.get("logic_version", "wc_risk_gates_v1")),
        dynamic_sizing=DynamicSizingConfig(
            enabled=bool(ds.get("enabled", True)),
            loss_reduction_pct=float(ds.get("loss_reduction_pct", 0.20)),
            loss_streak_threshold=int(ds.get("loss_streak_threshold", 2)),
            win_increase_pct=float(ds.get("win_increase_pct", 0.10)),
            win_streak_threshold=int(ds.get("win_streak_threshold", 3)),
            win_streak_cap=int(ds.get("win_streak_cap", 5)),
            min_size_multiplier=float(ds.get("min_size_multiplier", 0.25)),
            max_size_multiplier=float(ds.get("max_size_multiplier", 1.25)),
        ),
        portfolio_gates=PortfolioGatesConfig(
            enabled=bool(pg.get("enabled", True)),
            daily_loss_pct=float(pg.get("daily_loss_pct", 0.05)),
            daily_pause_minutes=int(pg.get("daily_pause_minutes", 60)),
            monthly_loss_pct=float(pg.get("monthly_loss_pct", 0.15)),
            monthly_pause_days=int(pg.get("monthly_pause_days", 30)),
            peak_drawdown_pct=float(pg.get("peak_drawdown_pct", 0.25)),
            peak_pause_days=int(pg.get("peak_pause_days", 7)),
            total_loss_pct=float(pg.get("total_loss_pct", 0.40)),
        ),
    )
