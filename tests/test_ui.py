"""Tests for optional localhost UI (read-only)."""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from market_helpers import make_market
from world_cup_bot.config import Settings
from world_cup_bot.ui_data import calendar_payload, meta_payload, plan_payload
from world_cup_bot.ui_server import UiHandler, _index_bytes


def _settings() -> Settings:
    return Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://ws-subscriptions-clob.polymarket.com/ws/user",
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path="data/local/ledger.jsonl",
        operating_config="config/operating.yaml",
    )


def test_index_html_exists():
    body = _index_bytes()
    assert b"World Cup Bot" in body
    assert b"read-only" in body.lower() or b"Read-only" in body


def test_meta_payload():
    payload = meta_payload(_settings())
    assert payload["dry_run"] is True
    assert payload["logic_version"] == "wc_advance_lp_v3"


def test_calendar_payload_offline():
    payload = calendar_payload(_settings())
    assert "cancel_window" in payload
    assert payload["min_hours_before_kickoff"] == 10.0


def test_plan_payload_mocked():
    markets = [make_market("Turkey", mid=0.45)]
    with patch("world_cup_bot.ui_data.scanner.discover_advance_markets", return_value=markets):
        payload = plan_payload(_settings())
    assert "intents" in payload


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
