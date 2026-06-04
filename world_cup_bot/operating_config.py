"""Load operating thresholds from YAML (wiki invariants — not live prices)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import yaml

DEFAULT_OPERATING = Path(__file__).resolve().parent.parent / "config" / "operating.yaml"


@dataclass(frozen=True)
class CalendarOps:
    prefer_hours_before_kickoff: float


@dataclass(frozen=True)
class BilateralOps:
    high_mid: float
    low_mid: float


@dataclass(frozen=True)
class FillHandlerOps:
    exit_within_seconds: float
    queue_depletion_usd: float
    vol_drop_pct: float
    vol_cooldown_minutes: float
    exit_loss_ticks: int


@dataclass(frozen=True)
class LiquidityOps:
    """CLOB /book depth gates — auto-clear human_review when passes (optional)."""

    min_depth_within_reward_spread_usd: float  # bid-side band depth
    min_ask_depth_within_reward_spread_usd: float
    min_combined_book_depth_usd: float
    min_levels_per_side: int
    max_spread_cents: float | None
    auto_clear_human_review: bool


@dataclass(frozen=True)
class RiskOps:
    max_daily_adverse_fill_usd: float


@dataclass(frozen=True)
class PromotionOps:
    """Shadow → live LP promotion gates (DSR + MCPT heuristics)."""

    min_fills: int
    min_distinct_days: int
    min_dsr: float
    max_mcpt_p: float


@dataclass(frozen=True)
class OperatingConfig:
    calendar: CalendarOps
    bilateral: BilateralOps
    fill_handler: FillHandlerOps
    liquidity: LiquidityOps
    risk: RiskOps
    promotion: PromotionOps


def load_operating_config(path: Path | None = None) -> OperatingConfig:
    p = path or DEFAULT_OPERATING
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cal = raw.get("calendar") or {}
    bil = raw.get("bilateral") or {}
    fh = raw.get("fill_handler") or {}
    liq = raw.get("liquidity") or {}
    risk = raw.get("risk") or {}
    promo = raw.get("promotion") or {}

    return OperatingConfig(
        calendar=CalendarOps(
            prefer_hours_before_kickoff=float(cal.get("prefer_hours_before_kickoff", 24)),
        ),
        bilateral=BilateralOps(
            high_mid=float(bil.get("high_mid", 0.90)),
            low_mid=float(bil.get("low_mid", 0.10)),
        ),
        fill_handler=FillHandlerOps(
            exit_within_seconds=float(fh.get("exit_within_seconds", 60)),
            queue_depletion_usd=float(fh.get("queue_depletion_usd", 300)),
            vol_drop_pct=float(fh.get("vol_drop_pct", 0.25)),
            vol_cooldown_minutes=float(fh.get("vol_cooldown_minutes", 30)),
            exit_loss_ticks=int(fh.get("exit_loss_ticks", 1)),
        ),
        liquidity=LiquidityOps(
            min_depth_within_reward_spread_usd=float(
                liq.get(
                    "min_bid_depth_within_reward_spread_usd",
                    liq.get("min_depth_within_reward_spread_usd", 50),
                )
            ),
            min_ask_depth_within_reward_spread_usd=float(
                liq.get("min_ask_depth_within_reward_spread_usd", 15)
            ),
            min_combined_book_depth_usd=float(liq.get("min_combined_book_depth_usd", 150)),
            min_levels_per_side=int(liq.get("min_levels_per_side", 2)),
            max_spread_cents=(
                float(liq["max_spread_cents"]) if liq.get("max_spread_cents") is not None else None
            ),
            auto_clear_human_review=bool(liq.get("auto_clear_human_review", False)),
        ),
        risk=RiskOps(
            max_daily_adverse_fill_usd=float(risk.get("max_daily_adverse_fill_usd", 500)),
        ),
        promotion=PromotionOps(
            min_fills=int(promo.get("min_fills", 5)),
            min_distinct_days=int(promo.get("min_distinct_days", 3)),
            min_dsr=float(promo.get("min_dsr", 0.0)),
            max_mcpt_p=float(promo.get("max_mcpt_p", 0.10)),
        ),
    )


def apply_bilateral_threshold_override(
    operating: OperatingConfig,
    bilateral_threshold: float | None,
) -> OperatingConfig:
    """Map phase-router bilateral_threshold to high/low mid bands."""
    if bilateral_threshold is None:
        return operating
    high = float(bilateral_threshold)
    low = max(0.0, min(1.0, 1.0 - high))
    return replace(
        operating,
        bilateral=BilateralOps(high_mid=high, low_mid=low),
    )
