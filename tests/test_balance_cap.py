"""Tests for collateral balance capping."""

from __future__ import annotations

from world_cup_bot.balance_cap import cap_intents_to_collateral
from world_cup_bot.quoter import MarketSnapshot, QuoteIntent


def _intent(team: str, notional: float) -> QuoteIntent:
    snap = MarketSnapshot(
        mid=0.5,
        best_bid=0.48,
        best_ask=0.52,
        spread=0.04,
        rewards_min_shares=50.0,
        rewards_max_spread=4.5,
        hours_to_kickoff=100.0,
    )
    price = 0.5
    return QuoteIntent(
        team=team,
        side="YES",
        token_id="1",
        order_id=f"dry-{team.lower()}-yes",
        price=price,
        size_shares=max(50.0, notional / price),
        notional_usd=notional,
        dry_run=True,
        reason="test",
        snapshot=snap,
    )


def test_cap_scales_down_to_budget() -> None:
    intents = [_intent("A", 100.0), _intent("B", 100.0)]
    capped = cap_intents_to_collateral(intents, 88.0)
    assert capped
    assert sum(i.notional_usd for i in capped) <= 88.0 + 0.01
    assert len(capped) == 2


def test_cap_noop_when_under_budget() -> None:
    intents = [_intent("A", 20.0)]
    capped = cap_intents_to_collateral(intents, 100.0)
    assert capped == intents
