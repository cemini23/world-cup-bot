"""Tests for Data API → shock tape export."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from world_cup_bot.data_api_client import trade_to_shock_tick
from world_cup_bot.match_market_discovery import MatchMarket
from world_cup_bot.shock_tape_export import export_markets


def test_trade_to_shock_tick_seconds_timestamp():
    row = {"timestamp": 1700000000, "price": "0.42"}
    tick = trade_to_shock_tick(row, slug="epl-beat-test")
    assert tick["ts_ms"] == 1_700_000_000_000
    assert tick["price"] == 0.42
    assert tick["slug"] == "epl-beat-test"


def test_export_markets_writes_combined(tmp_path: Path):
    market = MatchMarket(
        slug="epl-export-test",
        question="Q",
        condition_id="0xcid",
        yes_token_id="y",
        no_token_id="n",
        event_slug="ev",
        search_query="epl beat",
        accepting_orders=True,
    )
    trades = [
        {"timestamp": 1700000000, "price": "0.40"},
        {"timestamp": 1700000060, "price": "0.38"},
    ]

    with patch("world_cup_bot.shock_tape_export.iter_market_trades", return_value=iter(trades)):
        stats = export_markets(
            [market],
            tmp_path,
            max_trades_per_market=100,
            data_api="https://data-api.example",
        )

    assert stats == {"markets": 1, "trades": 2, "markets_with_trades": 1}
    combined = tmp_path / "combined.jsonl"
    lines = [json.loads(ln) for ln in combined.read_text().splitlines()]
    assert len(lines) == 2
    assert all(row["slug"] == "epl-export-test" for row in lines)
