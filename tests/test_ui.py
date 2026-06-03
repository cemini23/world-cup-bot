"""Tests for optional localhost UI (read-only)."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from market_helpers import make_market
from world_cup_bot.config import Settings
from world_cup_bot.ui_data import calendar_payload, match_shock_payload, meta_payload, plan_payload
from world_cup_bot.ui_server import UiHandler, _index_bytes


def _settings() -> Settings:
    return Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://ws-subscriptions-clob.polymarket.com/ws/user",
        ws_market_url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
        data_api_url="https://data-api.polymarket.com",
        match_shock_tape_dir="data/local/shock_tapes",
        match_shock_ledger_path="data/local/match_shock_paper.jsonl",
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path="data/local/ledger.jsonl",
        operating_config="config/operating.yaml",
        cross_venue_config="config/cross_venue.yaml",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
        market_phases_config="config/market_phases.yaml",
    )


def test_index_html_exists():
    body = _index_bytes()
    assert b"World Cup Bot" in body
    assert b"read-only" in body.lower()
    assert b"Match shock" in body


def test_meta_payload():
    payload = meta_payload(_settings())
    assert payload["dry_run"] is True
    assert payload["logic_version"] == "wc_advance_lp_v4"
    assert payload["match_shock_version"] == "wc_match_shock_v1"
    assert payload["match_shock_enabled"] is False


def test_match_shock_payload_mocked():
    from world_cup_bot.match_market_discovery import MatchMarket

    sample = [
        MatchMarket(
            slug="epl-test-beat",
            question="Will Team A beat Team B?",
            condition_id="0xabc",
            yes_token_id="y",
            no_token_id="n",
            event_slug="ev",
            search_query="epl beat",
            accepting_orders=True,
        )
    ]
    with patch("world_cup_bot.ui_data.discover_match_markets", return_value=sample):
        payload = match_shock_payload(_settings())
    assert payload["market_count"] == 1
    assert payload["open_count"] == 1
    assert payload["markets"][0]["slug"] == "epl-test-beat"


def test_ui_match_shock_endpoint():
    original = UiHandler.settings_factory
    UiHandler.settings_factory = staticmethod(_settings)  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", 0), UiHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with patch("world_cup_bot.ui_data.discover_match_markets", return_value=[]):
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/api/match-shock", timeout=5
            ) as resp:
                data = json.loads(resp.read().decode())
        assert data["logic_version"] == "wc_match_shock_v1"
        assert "market_count" in data
    finally:
        server.shutdown()
        server.server_close()
        UiHandler.settings_factory = original


def test_calendar_payload_offline():
    payload = calendar_payload(_settings())
    assert "cancel_window" in payload
    assert payload["min_hours_before_kickoff"] == 10.0


def test_plan_payload_mocked():
    markets = [make_market("Turkey", mid=0.45)]
    with (
        patch("world_cup_bot.ui_data.scanner.discover_advance_markets", return_value=markets),
        patch(
            "world_cup_bot.ui_data.liquidity_scanner.liquidity_map_for_markets",
            return_value=(None, {}),
        ),
    ):
        payload = plan_payload(_settings())
    assert "intents" in payload
    assert payload["liquidity_gate"] is True


def test_ui_health_endpoint():
    original = UiHandler.settings_factory
    UiHandler.settings_factory = staticmethod(_settings)  # type: ignore[assignment]
    server = ThreadingHTTPServer(("127.0.0.1", 0), UiHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as resp:
            data = json.loads(resp.read().decode())
        assert data["ok"] is True
        assert data["read_only"] is True
    finally:
        server.shutdown()
        server.server_close()
        UiHandler.settings_factory = original
