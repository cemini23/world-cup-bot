"""DRY_RUN plan must not require L2 for cancel-replace / open-order fetch."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from market_helpers import make_market
from world_cup_bot.clob_auth import MissingClobAuthError
from world_cup_bot.config import Settings
from world_cup_bot.order_manager import fetch_wc_open_orders
from world_cup_bot.quoter import MarketSnapshot, QuoteIntent, submit_quotes


def _settings(**overrides) -> Settings:
    base = Settings.from_env()
    return replace(base, **overrides) if overrides else base


def test_fetch_open_orders_skips_without_l2_in_dry_run():
    settings = _settings(dry_run=True)
    market = make_market("Turkey", mid=0.45)
    with patch(
        "world_cup_bot.order_manager.load_clob_auth",
        side_effect=MissingClobAuthError("no L2"),
    ):
        assert fetch_wc_open_orders(settings, [market]) == []


def test_submit_quotes_dry_run_no_l2_with_markets():
    settings = _settings(dry_run=True)
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{
            **market.__dict__,
            "yes_token_id": "yes-tok",
            "no_token_id": "no-tok",
            "condition_id": "0x1",
        }
    )
    snap = MarketSnapshot.from_market(market)
    assert snap is not None
    intent = QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="yes-tok",
        order_id="dry-turkey-yes-abcd1234",
        price=0.44,
        size_shares=100.0,
        notional_usd=44.0,
        dry_run=True,
        reason="test",
        snapshot=snap,
    )
    with patch(
        "world_cup_bot.order_manager.load_clob_auth", side_effect=MissingClobAuthError("no L2")
    ):
        out = submit_quotes([intent], settings, markets=[market])
    assert out.posted_list == [intent]
