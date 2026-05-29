"""Quoter — build limit-order intents; DRY_RUN logs only (live CLOB on prod)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from world_cup_bot.config import Settings
from world_cup_bot.conviction import ConvictionConfig, ConvictionResult, TeamMode

Side = Literal["YES", "NO"]


@dataclass(frozen=True)
class QuoteIntent:
    team: str
    side: Side
    token_id: str
    price: float
    size_shares: float
    notional_usd: float
    dry_run: bool
    reason: str


def _tick_price(value: float) -> float:
    """Polymarket sports books typically tick at 0.01; clamp to valid range."""
    return max(0.01, min(0.99, round(value, 2)))


def _shares_for_notional(notional_usd: float, price: float, min_shares: float) -> float:
    if price <= 0:
        return 0.0
    shares = notional_usd / price
    return max(min_shares, round(shares, 2))


def build_quotes(
    result: ConvictionResult,
    config: ConvictionConfig,
    settings: Settings,
) -> list[QuoteIntent]:
    """Resting limit bids from live Gamma book — no hardcoded mids."""
    market = result.market
    if not result.quote or market.mid is None:
        return []

    max_notional = config.max_notional(market.team)
    min_shares = market.rewards_min_shares or config.limits.min_reward_shares
    dry = settings.dry_run

    yes_price = _tick_price(market.best_bid if market.best_bid is not None else market.mid - 0.01)
    no_ref = (1.0 - market.mid) if market.mid is not None else None
    no_bid_implied = (1.0 - (market.best_ask or market.mid)) if market.best_ask else None
    no_price = _tick_price(no_bid_implied if no_bid_implied is not None else (no_ref or 0.5) - 0.01)

    bilateral = result.mode == TeamMode.BILATERAL_ONLY or market.bilateral_mode
    if bilateral:
        yes_ratio = 0.5
        no_ratio = 0.5
    else:
        yes_ratio = config.limits.yes_size_ratio
        no_ratio = 1.0 - yes_ratio

    yes_notional = max_notional * yes_ratio
    no_notional = max_notional * no_ratio

    intents: list[QuoteIntent] = [
        QuoteIntent(
            team=market.team,
            side="YES",
            token_id=market.yes_token_id,
            price=yes_price,
            size_shares=_shares_for_notional(yes_notional, yes_price, min_shares),
            notional_usd=yes_notional,
            dry_run=dry,
            reason=result.reason,
        )
    ]

    if bilateral and no_notional > 0:
        intents.append(
            QuoteIntent(
                team=market.team,
                side="NO",
                token_id=market.no_token_id,
                price=no_price,
                size_shares=_shares_for_notional(no_notional, no_price, min_shares),
                notional_usd=no_notional,
                dry_run=dry,
                reason="mandatory NO leg (bilateral mode)",
            )
        )

    return intents


def submit_quotes(intents: list[QuoteIntent], settings: Settings) -> list[QuoteIntent]:
    """Post to CLOB when DRY_RUN=false; prod wiring uses cemini-egress-fi."""
    if settings.dry_run:
        return intents
    raise NotImplementedError(
        "Live CLOB POST not enabled in public OSS — set DRY_RUN=true or use Cemini module"
    )
