"""Tests for Gamma match-market discovery (Module 8)."""

from __future__ import annotations

import json
from pathlib import Path

from world_cup_bot.match_market_discovery import (
    MatchMarket,
    discover_match_markets,
    load_discovery_json,
    parse_match_market,
    write_discovery_json,
)


def _fake_opener(payload: dict):
    class _Resp:
        def read(self):
            return json.dumps(payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(url, timeout=30):
        return _Resp()

    return opener


def test_parse_match_market_beat_slug():
    market = {
        "slug": "will-finland-beat-poland-on-2025-03-25",
        "question": "Will Finland beat Poland?",
        "conditionId": "0xabc123",
        "clobTokenIds": '["yes123", "no456"]',
        "acceptingOrders": True,
    }
    parsed = parse_match_market(market, event_slug="finland-poland", search_query="beat")
    assert parsed is not None
    assert parsed.slug.startswith("will-finland-beat")
    assert parsed.yes_token_id == "yes123"
    assert parsed.condition_id == "0xabc123"


def test_parse_match_market_rejects_advance_slug():
    market = {
        "slug": "will-brazil-advance-to-knockout",
        "conditionId": "0x1",
        "clobTokenIds": '["y", "n"]',
    }
    assert parse_match_market(market) is None


def test_discover_match_markets_dedupes_by_condition_id():
    payload = {
        "events": [
            {
                "slug": "epl-event",
                "markets": [
                    {
                        "slug": "epl-arsenal-beat-chelsea-2025-04-01",
                        "question": "Arsenal beat Chelsea?",
                        "conditionId": "0xdup",
                        "clobTokenIds": ["yes1", "no1"],
                    },
                    {
                        "slug": "epl-arsenal-beat-chelsea-2025-04-01-alt",
                        "question": "duplicate",
                        "conditionId": "0xdup",
                        "clobTokenIds": ["yes1", "no1"],
                    },
                ],
            }
        ]
    }
    markets = discover_match_markets(
        "https://gamma.example",
        opener=_fake_opener(payload),
        search_queries=("epl beat",),
    )
    assert len(markets) == 1


def test_discovery_json_roundtrip(tmp_path: Path):
    markets = [
        MatchMarket(
            slug="epl-test-beat",
            question="Q?",
            condition_id="0x1",
            yes_token_id="y",
            no_token_id="n",
            event_slug="ev",
            search_query="epl beat",
            accepting_orders=True,
        )
    ]
    path = tmp_path / "discovery.json"
    write_discovery_json(markets, path)
    loaded = load_discovery_json(path)
    assert len(loaded) == 1
    assert loaded[0].slug == "epl-test-beat"
    assert loaded[0].yes_token_id == "y"
