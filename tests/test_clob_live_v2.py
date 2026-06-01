"""Tests for py-clob-client-v2 integration in clob_live."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from world_cup_bot.clob_live import (
    LiveClobPostError,
    build_clob_client,
    cancel_order_id,
    order_options_for_token,
    post_quote_intent,
)
from world_cup_bot.config import Settings
from world_cup_bot.quoter import MarketSnapshot, QuoteIntent


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        mid=0.56,
        best_bid=0.54,
        best_ask=0.58,
        spread=0.04,
        rewards_min_shares=50.0,
        rewards_max_spread=4.5,
        hours_to_kickoff=100.0,
    )


def _intent(**overrides) -> QuoteIntent:
    base = dict(
        team="USA",
        side="YES",
        token_id="tok-usa",
        order_id="dry-usa",
        price=0.55,
        size_shares=100.0,
        notional_usd=55.0,
        dry_run=False,
        reason="test",
        snapshot=_snapshot(),
    )
    base.update(overrides)
    return QuoteIntent(**base)


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "11" * 32)
    monkeypatch.setenv("POLYMARKET_API_KEY", "k")
    monkeypatch.setenv("POLYMARKET_API_SECRET", "s")
    monkeypatch.setenv("POLYMARKET_API_PASSPHRASE", "p")
    monkeypatch.setenv("POLYMARKET_BUILDER_CODE", "0x" + "22" * 32)
    monkeypatch.setenv("POLYMARKET_FUNDER_ADDRESS", "0x" + "33" * 20)
    return Settings.from_env()


def test_build_clob_client_passes_builder_and_server_time(settings, monkeypatch):
    captured: dict = {}

    class FakeClobClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("py_clob_client_v2.client.ClobClient", FakeClobClient)

    build_clob_client(settings)
    assert captured["use_server_time"] is True
    assert captured["retry_on_error"] is True
    assert captured["builder_config"] is not None
    assert captured["builder_config"].builder_code == "0x" + "22" * 32


def test_order_options_for_token_fetches_tick_and_neg_risk():
    client = MagicMock()
    client.get_tick_size.return_value = "0.01"
    client.get_neg_risk.return_value = False
    opts = order_options_for_token(client, "tok-1")
    assert opts.tick_size == "0.01"
    assert opts.neg_risk is False
    client.get_tick_size.assert_called_once_with("tok-1")
    client.get_neg_risk.assert_called_once_with("tok-1")


def test_post_quote_intent_uses_dynamic_options():
    client = MagicMock()
    client.get_tick_size.return_value = "0.001"
    client.get_neg_risk.return_value = True
    client.create_order.return_value = {"signed": True}
    client.post_order.return_value = {"orderID": "abc", "success": True}

    resp = post_quote_intent(client, _intent())
    assert resp["orderID"] == "abc"
    _order_args, options = client.create_order.call_args[0]
    assert options.tick_size == "0.001"
    assert options.neg_risk is True
    client.post_order.assert_called_once()


def test_cancel_order_id_uses_order_payload():
    client = MagicMock()
    client.cancel_order.return_value = {"canceled": ["x"]}
    cancel_order_id(client, "order-123")
    payload = client.cancel_order.call_args[0][0]
    assert payload.orderID == "order-123"


def test_order_version_mismatch_maps_to_live_clob_post_error():
    from py_clob_client_v2.exceptions import PolyApiException

    client = MagicMock()
    client.get_tick_size.return_value = "0.01"
    client.get_neg_risk.return_value = False
    client.create_order.return_value = {"signed": True}
    client.post_order.side_effect = PolyApiException(error_msg={"error": "order_version_mismatch"})

    with pytest.raises(LiveClobPostError, match="order_version_mismatch"):
        post_quote_intent(client, _intent())
