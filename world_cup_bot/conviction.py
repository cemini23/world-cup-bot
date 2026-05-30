"""Conviction filter — YAML team tiers + mid band gates (no hardcoded prices)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml

from world_cup_bot import team_names
from world_cup_bot.liquidity_scanner import LiquidityReport
from world_cup_bot.operating_config import LiquidityOps
from world_cup_bot.scanner import AdvanceMarket

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "conviction.yaml"


class TeamMode(StrEnum):
    YES_HEAVY = "yes_heavy"
    BILATERAL_ONLY = "bilateral_only"
    FADE_WATCH = "fade_watch"
    SKIP = "skip"
    HUMAN_REVIEW = "human_review"
    UNLISTED = "unlisted"


@dataclass(frozen=True)
class Limits:
    min_mid: float = 0.20
    max_mid: float = 0.80
    bilateral_mid: float = 0.90
    default_max_notional_usd: float = 2000.0
    yes_size_ratio: float = 0.70
    min_reward_shares: float = 500.0


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

        return self.underlying_team_mode(team)

    def underlying_team_mode(self, team: str) -> TeamMode:
        """Tier from YAML lists only — ignores per_team.mode (e.g. human_review)."""
        canon = team_names.normalize_team(team)
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


def evaluate_market(
    market: AdvanceMarket,
    config: ConvictionConfig,
    *,
    liquidity: LiquidityReport | None = None,
    liquidity_cfg: LiquidityOps | None = None,
    liquidity_gate: bool = False,
) -> ConvictionResult:
    mode = config.team_mode(market.team)

    if mode == TeamMode.SKIP:
        return ConvictionResult(market, mode, False, "per_team mode=skip")
    if mode == TeamMode.HUMAN_REVIEW:
        cleared = _try_clear_human_review(
            market,
            config,
            liquidity=liquidity,
            liquidity_cfg=liquidity_cfg,
            liquidity_gate=liquidity_gate,
        )
        if cleared is None:
            hint = ""
            if liquidity is not None:
                status = "PASS" if liquidity.passes else "FAIL"
                hint = f" (CLOB depth {status}: {'; '.join(liquidity.reasons[:2])})"
            return ConvictionResult(
                market,
                mode,
                False,
                f"human_review — operator gate required (K84 LP safety){hint}",
            )
        return cleared
    if mode == TeamMode.FADE_WATCH:
        return ConvictionResult(market, mode, False, "fade_watch — alert only")
    if mode == TeamMode.UNLISTED:
        return ConvictionResult(market, mode, False, "not in conviction YAML")
    if not market.kickoff_known:
        return ConvictionResult(market, mode, False, "unknown kickoff — fail closed")
    if not market.rewards_params_ok:
        return ConvictionResult(market, mode, False, "missing Gamma reward params")
    if (
        market.rewards_min_shares is not None
        and market.rewards_min_shares < config.limits.min_reward_shares
    ):
        return ConvictionResult(
            market,
            mode,
            False,
            f"rewardsMinSize {market.rewards_min_shares:.0f} "
            f"< config floor {config.limits.min_reward_shares:.0f}",
        )
    if not market.lp_eligible:
        return ConvictionResult(
            market, mode, False, "failed LP eligibility (calendar/spread/rewards)"
        )

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


def _try_clear_human_review(
    market: AdvanceMarket,
    config: ConvictionConfig,
    *,
    liquidity: LiquidityReport | None,
    liquidity_cfg: LiquidityOps | None,
    liquidity_gate: bool,
) -> ConvictionResult | None:
    """When liquidity gate passes, evaluate using underlying tier (not human_review)."""
    if liquidity_cfg is None or liquidity is None:
        return None
    if not liquidity_gate and not liquidity_cfg.auto_clear_human_review:
        return None
    if not liquidity.passes:
        return None

    underlying = config.underlying_team_mode(market.team)
    if underlying in (TeamMode.UNLISTED, TeamMode.FADE_WATCH, TeamMode.SKIP):
        return None

    result = _evaluate_tier(market, config, underlying)
    if not result.quote:
        return ConvictionResult(
            market,
            TeamMode.HUMAN_REVIEW,
            False,
            f"human_review liquidity PASS but tier blocked: {result.reason}",
        )
    return ConvictionResult(
        market,
        TeamMode.HUMAN_REVIEW,
        True,
        f"human_review cleared by CLOB depth — {result.reason}",
    )


def _evaluate_tier(
    market: AdvanceMarket,
    config: ConvictionConfig,
    mode: TeamMode,
) -> ConvictionResult:
    if not market.kickoff_known:
        return ConvictionResult(market, mode, False, "unknown kickoff — fail closed")
    if not market.rewards_params_ok:
        return ConvictionResult(market, mode, False, "missing Gamma reward params")
    if (
        market.rewards_min_shares is not None
        and market.rewards_min_shares < config.limits.min_reward_shares
    ):
        return ConvictionResult(
            market,
            mode,
            False,
            f"rewardsMinSize {market.rewards_min_shares:.0f} "
            f"< config floor {config.limits.min_reward_shares:.0f}",
        )
    if not market.lp_eligible:
        return ConvictionResult(
            market, mode, False, "failed LP eligibility (calendar/spread/rewards)"
        )

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
    liquidity_by_team: dict[str, LiquidityReport] | None = None,
    liquidity_cfg: LiquidityOps | None = None,
    liquidity_gate: bool = False,
) -> list[ConvictionResult]:
    results = [
        evaluate_market(
            m,
            config,
            liquidity=(liquidity_by_team or {}).get(m.team),
            liquidity_cfg=liquidity_cfg,
            liquidity_gate=liquidity_gate,
        )
        for m in markets
    ]
    if quote_only:
        return [r for r in results if r.quote]
    return results
