"""Quoter — build limit-order intents; DRY_RUN logs only (live CLOB on prod)."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from world_cup_bot.config import Settings
from world_cup_bot.conviction import ConvictionConfig, ConvictionResult, TeamMode
from world_cup_bot.scanner import AdvanceMarket

if TYPE_CHECKING:
    from world_cup_bot.logic_version import StrategyVersionSpec
    from world_cup_bot.order_manager import TradingHalt

logger = logging.getLogger(__name__)

Side = Literal["YES", "NO"]


@dataclass(frozen=True)
class MarketSnapshot:
    """Book + reward state at quote time (K75 replay / Phase-0 place-time logging)."""

    mid: float
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    rewards_min_shares: float
    rewards_max_spread: float
    hours_to_kickoff: float | None

    @classmethod
    def from_market(cls, market: AdvanceMarket) -> MarketSnapshot | None:
        if market.mid is None:
            return None
        if market.rewards_min_shares is None or market.rewards_max_spread is None:
            return None
        return cls(
            mid=market.mid,
            best_bid=market.best_bid,
            best_ask=market.best_ask,
            spread=market.spread,
            rewards_min_shares=market.rewards_min_shares,
            rewards_max_spread=market.rewards_max_spread,
            hours_to_kickoff=market.hours_to_kickoff,
        )


@dataclass(frozen=True)
class QuoteIntent:
    team: str
    side: Side
    token_id: str
    order_id: str
    price: float
    size_shares: float
    notional_usd: float
    dry_run: bool
    reason: str
    snapshot: MarketSnapshot


def _tick_price(value: float) -> float:
    """Polymarket sports books typically tick at 0.01; clamp to valid range."""
    return max(0.01, min(0.99, round(value, 2)))


def _max_spread_distance(max_spread_cents: float) -> float:
    """Gamma rewardsMaxSpread is in cents (e.g. 4.5 → ±4.5¢ from midpoint)."""
    return max_spread_cents / 100.0


def _clamp_yes_bid(bid: float, mid: float, max_spread_cents: float) -> float:
    floor = mid - _max_spread_distance(max_spread_cents)
    return _tick_price(max(bid, floor))


def _clamp_no_bid(bid: float, yes_mid: float, max_spread_cents: float) -> float:
    no_mid = 1.0 - yes_mid
    floor = no_mid - _max_spread_distance(max_spread_cents)
    return _tick_price(max(bid, floor))


def _shares_for_notional(notional_usd: float, price: float, min_shares: float) -> float:
    if price <= 0:
        return 0.0
    shares = notional_usd / price
    return max(min_shares, round(shares, 2))


def _new_order_id(team: str, side: Side, *, dry_run: bool) -> str:
    prefix = "dry" if dry_run else "live"
    slug = team.lower().replace(" ", "-")[:20]
    return f"{prefix}-{slug}-{side.lower()}-{secrets.token_hex(4)}"


def build_quotes(
    result: ConvictionResult,
    config: ConvictionConfig,
    settings: Settings,
    *,
    notional_multiplier: float = 1.0,
    max_notional_multiplier: float = 1.0,
) -> list[QuoteIntent]:
    """Resting limit bids from live Gamma book — no hardcoded mids."""
    market = result.market
    if not result.quote or market.mid is None:
        return []

    snapshot = MarketSnapshot.from_market(market)
    if snapshot is None:
        return []

    cap_mult = max(1.0, max_notional_multiplier)
    scale = max(0.0, min(cap_mult, notional_multiplier))
    yaml_cap = config.max_notional(market.team) * scale
    env_cap = settings.max_notional_per_market_usd
    max_notional = min(yaml_cap, env_cap) if env_cap > 0 else yaml_cap
    if max_notional <= 0:
        return []
    min_shares = snapshot.rewards_min_shares
    dry = settings.dry_run
    max_spread = snapshot.rewards_max_spread

    preferred_yes = market.best_bid if market.best_bid is not None else market.mid - 0.01
    yes_price = _clamp_yes_bid(preferred_yes, market.mid, max_spread)

    no_bid_implied = (1.0 - (market.best_ask or market.mid)) if market.best_ask else None
    no_ref = 1.0 - market.mid
    preferred_no = no_bid_implied if no_bid_implied is not None else no_ref - 0.01
    no_price = _clamp_no_bid(preferred_no, market.mid, max_spread)

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
            order_id=_new_order_id(market.team, "YES", dry_run=dry),
            price=yes_price,
            size_shares=_shares_for_notional(yes_notional, yes_price, min_shares),
            notional_usd=yes_notional,
            dry_run=dry,
            reason=result.reason,
            snapshot=snapshot,
        )
    ]

    if bilateral and no_notional > 0:
        intents.append(
            QuoteIntent(
                team=market.team,
                side="NO",
                token_id=market.no_token_id,
                order_id=_new_order_id(market.team, "NO", dry_run=dry),
                price=no_price,
                size_shares=_shares_for_notional(no_notional, no_price, min_shares),
                notional_usd=no_notional,
                dry_run=dry,
                reason="mandatory NO leg (bilateral mode)",
                snapshot=snapshot,
            )
        )

    return intents


def submit_quotes(
    intents: list[QuoteIntent],
    settings: Settings,
    *,
    markets: list[AdvanceMarket] | None = None,
    halt: TradingHalt | None = None,
    ledger_path: str | None = None,
    version_spec: StrategyVersionSpec | None = None,
) -> list[QuoteIntent]:
    """Post to CLOB when DRY_RUN=false; cancel-replace stale orders first."""
    if not intents:
        return intents

    if halt is not None:
        intents = [i for i in intents if not halt.is_halted(i.team)]
        if not intents:
            return []

    if markets is not None and not settings.dry_run:
        from world_cup_bot.operating_config import load_operating_config
        from world_cup_bot.wiki_enforcement import enforce_or_raise

        operating = load_operating_config(Path(settings.operating_config))
        enforce_or_raise(intents, settings, markets, operating)

    if markets is not None:
        from world_cup_bot.order_manager import cancel_replace_before_submit

        cancel_replace_before_submit(
            settings,
            markets,
            intents,
            ledger_path=ledger_path,
            version_spec=version_spec,
        )

    if settings.dry_run:
        for intent in intents:
            logger.info(
                "QUOTE_DRY %s %s @ %.2f x %.1f",
                intent.team,
                intent.side,
                intent.price,
                intent.size_shares,
            )
        return intents

    from world_cup_bot.preflight import assert_live_post_allowed

    assert_live_post_allowed(settings)

    from world_cup_bot.clob_live import LiveClobPostError, build_clob_client, post_quote_intent

    client = build_clob_client(settings)
    posted: list[QuoteIntent] = []
    for intent in intents:
        try:
            post_quote_intent(client, intent)
            posted.append(intent)
        except LiveClobPostError as exc:
            msg = str(exc).lower()
            if "crosses book" in msg or "not enough balance / allowance" in msg:
                logger.warning(
                    "quote POST skipped %s %s: %s",
                    intent.team,
                    intent.side,
                    exc,
                )
                continue
            raise RuntimeError(f"quote POST failed for {intent.team} {intent.side}: {exc}") from exc
    return posted
