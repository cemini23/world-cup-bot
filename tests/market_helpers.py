"""Shared test helpers for AdvanceMarket fixtures."""

from __future__ import annotations

from world_cup_bot import scanner


def make_market(
    team: str,
    *,
    mid: float,
    lp_eligible: bool = True,
    bilateral: bool = False,
    hours_to_kickoff: float | None = 48.0,
    rewards_min_shares: float | None = 500.0,
    rewards_max_spread: float | None = 4.5,
    min_hours: float = 10.0,
) -> scanner.AdvanceMarket:
    must_cancel = hours_to_kickoff is not None and hours_to_kickoff < min_hours
    return scanner.AdvanceMarket(
        team=team,
        question=f"Will {team} advance to the knockout stages at the 2026 FIFA World Cup?",
        slug=team.lower(),
        condition_id="0x1",
        yes_token_id="yes",
        no_token_id="no",
        best_bid=mid - 0.02,
        best_ask=mid + 0.02,
        spread=0.04,
        mid=mid,
        rewards_min_shares=rewards_min_shares,
        rewards_max_spread=rewards_max_spread,
        liquidity=5000.0,
        volume=1000.0,
        accepting_orders=True,
        hours_to_kickoff=hours_to_kickoff,
        must_cancel=must_cancel,
        bilateral_mode=bilateral or mid > 0.90 or mid < 0.10,
        min_hours_before_kickoff=min_hours,
    )
