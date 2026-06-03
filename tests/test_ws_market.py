"""Tests for CLOB market-channel WebSocket parsing (Module 8)."""

from __future__ import annotations

import json

from world_cup_bot.ws_market import (
    build_market_subscription,
    extract_market_ticks,
    parse_market_ws_text,
)


def test_build_market_subscription():
    sub = build_market_subscription(["tok-a", "tok-b"])
    assert sub == {"assets_ids": ["tok-a", "tok-b"], "type": "market"}


def test_parse_market_ws_text_pong():
    assert parse_market_ws_text("PONG") is None


def test_extract_book_event_mid_price():
    msg = {
        "event_type": "book",
        "asset_id": "tok-yes",
        "timestamp": 1_700_000_000_000,
        "bids": [{"price": "0.44", "size": "100"}],
        "asks": [{"price": "0.46", "size": "50"}],
    }
    ticks = extract_market_ticks(msg, asset_to_slug={"tok-yes": "epl-team-beat"})
    assert len(ticks) == 1
    assert ticks[0]["slug"] == "epl-team-beat"
    assert ticks[0]["price"] == 0.45
    assert ticks[0]["ts_ms"] == 1_700_000_000_000
    assert len(ticks[0]["bids"]) == 1


def test_extract_price_change_event():
    msg = {
        "event_type": "price_change",
        "timestamp": 1700000000,
        "price_changes": [
            {"asset_id": "tok-yes", "price": "0.32"},
        ],
    }
    ticks = extract_market_ticks(msg, asset_to_slug={"tok-yes": "wc-beat-slug"})
    assert len(ticks) == 1
    assert ticks[0]["price"] == 0.32
    assert ticks[0]["ts_ms"] == 1_700_000_000_000


def test_extract_list_payload():
    raw = json.dumps(
        [
            {"event_type": "book", "asset_id": "a1", "price": "0.5", "bids": [], "asks": []},
        ]
    )
    msg = parse_market_ws_text(raw)
    assert isinstance(msg, list)
    ticks = extract_market_ticks(msg, asset_to_slug={"a1": "slug-a"})
    assert len(ticks) == 1
    assert ticks[0]["price"] == 0.5
