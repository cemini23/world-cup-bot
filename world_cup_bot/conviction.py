"""Conviction filter — YAML team tiers + mid band gates (no hardcoded prices)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml

from world_cup_bot import team_names
from world_cup_bot.scanner import AdvanceMarket

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "conviction.yaml"


class TeamMode(StrEnum):
    YES_HEAVY = "yes_heavy"
    BILATERAL_ONLY = "bilateral_only"
    FADE_WATCH = "fade_watch"
    SKIP = "skip"
    UNLISTED = "unlisted"


@dataclass(frozen=True)
class Limits:
    min_mid: float = 0.20
    max_mid: float = 0.80
    bilateral_mid: float = 0.90
    default_max_notional_usd: float = 2000.0
    yes_size_ratio: float = 0.70
    min_reward_shares: float = 50.0


@dataclass(frozen=True)
class TeamOverride:
    max_notional_usd: float | None = None
    mode: TeamMode | None = None


@dataclass(frozen=True)
class ConvictionConfig:
    yes_conviction: frozenset[str]
    bilateral_only: frozenset[str]
    fade_watch: frozenset[str]
    limits: Limits
    per_team: dict[str, TeamOverride] = field(default_factory=dict)

    def team_mode(self, team: str) -> TeamMode:
        canon = team_names.normalize_team(team)
        override = self.per_team.get(canon)
        if override and override.mode:
            return override.mode

        if _in_set(canon, self.fade_watch):
            return TeamMode.FADE_WATCH
        if _in_set(canon, self.yes_conviction):
            return TeamMode.YES_HEAVY
        if _in_set(canon, self.bilateral_only):
            return TeamMode.BILATERAL_ONLY
        return TeamMode.UNLISTED

    def max_notional(self, team: str) -> float:
        canon = team_names.normalize_team(team)
        override = self.per_team.get(canon)
        if override and override.max_notional_usd is not None:
            return override.max_notional_usd
        return self.limits.default_max_notional_usd


def _in_set(team: str, names: frozenset[str]) -> bool:
    canon = team_names.normalize_team(team)
    for name in names:
        if team_names.teams_match(name, canon):
            return True
    return False


def _normalize_name_list(items: list[str] | None) -> frozenset[str]:
    if not items:
        return frozenset()
    return frozenset(team_names.normalize_team(x) for x in items)


def load_conviction_config(path: Path | None = None) -> ConvictionConfig:
    p = path or DEFAULT_CONFIG
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    limits_raw = raw.get("limits") or {}
    limits = Limits(
        min_mid=float(limits_raw.get("min_mid", 0.20)),
        max_mid=float(limits_raw.get("max_mid", 0.80)),
        bilateral_mid=float(limits_raw.get("bilateral_mid", 0.90)),
        default_max_notional_usd=float(limits_raw.get("default_max_notional_usd", 2000)),
        yes_size_ratio=float(limits_raw.get("yes_size_ratio", 0.70)),
        min_reward_shares=float(limits_raw.get("min_reward_shares", 50)),
    )

    per_team: dict[str, TeamOverride] = {}
    for team, spec in (raw.get("per_team") or {}).items():
        mode_str = spec.get("mode")
        mode = TeamMode(mode_str) if mode_str else None
        per_team[team_names.normalize_team(team)] = TeamOverride(
            max_notional_usd=spec.get("max_notional_usd"),
            mode=mode,
        )

    return ConvictionConfig(
        yes_conviction=_normalize_name_list(raw.get("yes_conviction")),
        bilateral_only=_normalize_name_list(raw.get("bilateral_only")),
        fade_watch=_normalize_name_list(raw.get("fade_watch")),
        limits=limits,
        per_team=per_team,
    )


@dataclass(frozen=True)
class ConvictionResult:
    market: AdvanceMarket
    mode: TeamMode
    quote: bool
    reason: str


def evaluate_market(market: AdvanceMarket, config: ConvictionConfig) -> ConvictionResult:
    mode = config.team_mode(market.team)

    if mode == TeamMode.SKIP:
        return ConvictionResult(market, mode, False, "per_team mode=skip")
    if mode == TeamMode.FADE_WATCH:
        return ConvictionResult(market, mode, False, "fade_watch — alert only")
    if mode == TeamMode.UNLISTED:
        return ConvictionResult(market, mode, False, "not in conviction YAML")
    if not market.lp_eligible:
        return ConvictionResult(market, mode, False, "failed LP eligibility (calendar/spread)")

    mid = market.mid
    if mid is None:
        return ConvictionResult(market, mode, False, "no mid from Gamma")

    lim = config.limits
    if mode == TeamMode.YES_HEAVY:
        if market.bilateral_mode or mid >= lim.bilateral_mid:
            return ConvictionResult(
                market, mode, True, "yes_heavy → bilateral (mid ≥ bilateral threshold)"
            )
        if mid < lim.min_mid or mid > lim.max_mid:
            return ConvictionResult(
                market,
                mode,
                False,
                f"mid {mid:.3f} outside [{lim.min_mid}, {lim.max_mid}]",
            )
        return ConvictionResult(market, mode, True, "yes_heavy mid-band match")

    if mode == TeamMode.BILATERAL_ONLY:
        if market.bilateral_mode or mid >= lim.bilateral_mid:
            return ConvictionResult(market, mode, True, "bilateral_only high mid")
        return ConvictionResult(
            market, mode, False, f"mid {mid:.3f} below bilateral {lim.bilateral_mid}"
        )

    return ConvictionResult(market, mode, False, "unhandled mode")


def filter_conviction_markets(
    markets: list[AdvanceMarket],
    config: ConvictionConfig,
    *,
    quote_only: bool = True,
) -> list[ConvictionResult]:
    results = [evaluate_market(m, config) for m in markets]
    if quote_only:
        return [r for r in results if r.quote]
    return results
