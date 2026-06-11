"""Unified trading mode — LP pre-kickoff, shock in-play, OFF otherwise.

One bot, two strategies, handoff at the calendar cancel window:
  - **advance** markets → LP while hours_to_kickoff ≥ min_hours; OFF inside cancel window + live
  - **match** markets → OFF pre-kickoff; SHOCK from kickoff until match_end_hours

Advance LP and match shock share fixtures + cancel threshold but never quote simultaneously
on the same market slug.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MarketKind(StrEnum):
    ADVANCE = "advance"
    MATCH = "match"


class TradingMode(StrEnum):
    LP = "lp"
    SHOCK = "shock"
    OFF = "off"


@dataclass(frozen=True)
class ModeHandoffConfig:
    min_hours_before_kickoff: float = 10.0
    prefer_hours_before_kickoff: float = 24.0
    max_match_hours: float = 2.0
    shock_enabled: bool = False


@dataclass(frozen=True)
class ModeDecision:
    mode: TradingMode
    market_kind: MarketKind
    hours_to_kickoff: float | None
    reason: str

    @property
    def lp_active(self) -> bool:
        return self.mode == TradingMode.LP

    @property
    def shock_active(self) -> bool:
        return self.mode == TradingMode.SHOCK


def resolve_trading_mode(
    *,
    market_kind: MarketKind,
    hours_to_kickoff: float | None,
    cfg: ModeHandoffConfig | None = None,
) -> ModeDecision:
    """Return LP, SHOCK, or OFF for a market at the current clock."""
    c = cfg or ModeHandoffConfig()

    if market_kind == MarketKind.ADVANCE:
        return _resolve_advance(hours_to_kickoff, c)
    return _resolve_match(hours_to_kickoff, c)


def _resolve_advance(hours: float | None, cfg: ModeHandoffConfig) -> ModeDecision:
    if hours is None:
        return ModeDecision(
            TradingMode.OFF,
            MarketKind.ADVANCE,
            None,
            "unknown_kickoff",
        )
    if hours >= cfg.min_hours_before_kickoff:
        return ModeDecision(
            TradingMode.LP,
            MarketKind.ADVANCE,
            hours,
            "pregame_lp_window",
        )
    return ModeDecision(
        TradingMode.OFF,
        MarketKind.ADVANCE,
        hours,
        "cancel_window_or_live",
    )


def _resolve_match(hours: float | None, cfg: ModeHandoffConfig) -> ModeDecision:
    if hours is None:
        return ModeDecision(
            TradingMode.OFF,
            MarketKind.MATCH,
            None,
            "unknown_kickoff",
        )
    if hours > 0:
        return ModeDecision(
            TradingMode.OFF,
            MarketKind.MATCH,
            hours,
            "pregame_no_shock",
        )
    if not cfg.shock_enabled:
        return ModeDecision(
            TradingMode.OFF,
            MarketKind.MATCH,
            hours,
            "shock_disabled",
        )
    elapsed_hours = -hours
    if elapsed_hours >= cfg.max_match_hours:
        return ModeDecision(
            TradingMode.OFF,
            MarketKind.MATCH,
            hours,
            "post_match",
        )
    return ModeDecision(
        TradingMode.SHOCK,
        MarketKind.MATCH,
        hours,
        "in_play_shock_window",
    )


def infer_market_kind_from_slug(slug: str) -> MarketKind:
    """Heuristic slug classifier for mode routing."""
    s = slug.lower()
    blocked = (
        "advance",
        "knockout",
        "group-winner",
        "to-win-the-world-cup",
        "win-the-world-cup",
    )
    if any(tok in s for tok in blocked):
        return MarketKind.ADVANCE
    match_tokens = (
        "fifwc-",  # WC 2026 fixture slugs (e.g. fifwc-mex-rsa-2026-06-11-mex)
        "world-cup",
        "fifa-world-cup",
        "wc-2026",
        "epl",
        "ucl",
        "champions-league",
        "la-liga",
        "vs-",
        "-vs-",
        "beat",
        "win-on",
    )
    if any(tok in s for tok in match_tokens):
        return MarketKind.MATCH
    return MarketKind.ADVANCE


def load_mode_handoff_from_settings(
    *,
    min_hours_before_kickoff: float,
    prefer_hours_before_kickoff: float = 24.0,
    max_match_hours: float = 2.0,
    shock_enabled: bool = False,
) -> ModeHandoffConfig:
    return ModeHandoffConfig(
        min_hours_before_kickoff=min_hours_before_kickoff,
        prefer_hours_before_kickoff=prefer_hours_before_kickoff,
        max_match_hours=max_match_hours,
        shock_enabled=shock_enabled,
    )
