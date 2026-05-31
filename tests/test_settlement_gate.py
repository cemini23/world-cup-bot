"""Tests for settlement gate (Module 1b PR2)."""

from __future__ import annotations

from world_cup_bot.settlement_gate import market_is_settled


def test_market_is_settled_closed():
    assert market_is_settled({"closed": True, "acceptingOrders": True}) is True


def test_market_is_settled_not_accepting():
    assert market_is_settled({"closed": False, "acceptingOrders": False}) is True


def test_market_is_settled_resolved_prices():
    assert (
        market_is_settled(
            {
                "closed": False,
                "acceptingOrders": True,
                "outcomePrices": ["1", "0"],
            }
        )
        is True
    )


def test_market_is_settled_open():
    assert (
        market_is_settled(
            {
                "closed": False,
                "acceptingOrders": True,
                "outcomePrices": ["0.55", "0.45"],
            }
        )
        is False
    )


def test_fetch_failure_fails_closed():
    from world_cup_bot.settlement_gate import PhaseSettlementStatus

    st = PhaseSettlementStatus(
        phase_id="group_advance", total_markets=0, settled_markets=0, fetch_failed=True
    )
    assert st.all_settled is False
