"""Tests for live plan token resolution and tape window."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from world_cup_bot.config import Settings
from world_cup_bot.match_market_discovery import MatchMarket
from world_cup_bot.match_shock_config import load_match_shock_config
from world_cup_bot.match_shock_plan import process_tape_once, run_plan_once

FIXTURE = Path(__file__).resolve().parents[0] / "fixtures" / "shock_replay" / "sample_trades.jsonl"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://example/ws/user",
        ws_market_url="wss://example/ws/market",
        data_api_url="https://data-api.polymarket.com",
        match_shock_tape_dir=str(tmp_path / "tapes"),
        match_shock_ledger_path=str(tmp_path / "shock.jsonl"),
        dry_run=False,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path=str(tmp_path / "ledger.jsonl"),
        operating_config="config/operating.yaml",
        cross_venue_config="config/cross_venue.yaml",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
        market_phases_config="config/market_phases.yaml",
    )


def test_live_uses_discovery_tokens_when_in_play_filter_empty(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("WC_SHOCK_ENABLED", "1")
    monkeypatch.setenv("WC_MATCH_SHOCK_LIVE", "1")
    monkeypatch.setenv("WC_MATCH_SHOCK_LIVE_ACK", "1")
    cfg = load_match_shock_config()
    market = MatchMarket(
        slug="epl-man-united-win-2025-04-01",
        question="q",
        condition_id="0xabc",
        yes_token_id="token-yes-123",
        no_token_id="token-no-456",
        event_slug="evt",
        search_query="q",
        accepting_orders=True,
    )
    submitted: list[str] = []

    def _fake_submit(*_a, **kw):
        submitted.append(kw["token_id"])
        return [{"order_id": "oid1"}]

    gate_ok = type("G", (), {"allowed": True, "reason": "ok"})()
    with patch("world_cup_bot.match_shock_plan._load_live_post_state", return_value={}):
        with patch("world_cup_bot.match_shock_plan.check_live_post_gates", return_value=gate_ok):
            with patch("world_cup_bot.match_shock_plan.submit_ladder", side_effect=_fake_submit):
                stats = process_tape_once(
                    FIXTURE,
                    markets=[],  # in-play filter empty
                    shock_cfg=cfg,
                    settings=settings,
                    ledger_path=tmp_path / "shock.jsonl",
                    live=True,
                    token_by_slug={market.slug: market.yes_token_id},
                    tape_slug_set=frozenset({market.slug}),
                )
    assert stats.live_posts >= 1
    assert submitted
    assert submitted[0] == "token-yes-123"


def test_run_plan_once_live_falls_back_to_discovery_markets(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("WC_SHOCK_ENABLED", "1")
    monkeypatch.setenv("WC_MATCH_SHOCK_LIVE", "1")
    monkeypatch.setenv("WC_MATCH_SHOCK_LIVE_ACK", "1")
    discover = tmp_path / "kickoff.json"
    discover.write_text(
        """{
  "markets": [{
    "slug": "epl-man-united-win-2025-04-01",
    "question": "q",
    "condition_id": "0xabc",
    "yes_token_id": "token-yes-123",
    "no_token_id": "token-no-456",
    "event_slug": "evt",
    "search_query": "q",
    "accepting_orders": true
  }]
}""",
        encoding="utf-8",
    )
    with patch("world_cup_bot.match_shock_plan.process_tape_once") as proc:
        proc.return_value = type(
            "S",
            (),
            {
                "shocks": 0,
                "ladders": 0,
                "paper_fills": 0,
                "live_posts": 0,
                "slugs_scanned": 1,
                "last_run_at": "",
                "errors": [],
            },
        )()
        run_plan_once(
            settings,
            discover_json=discover,
            tape_path=FIXTURE,
            ledger_path=tmp_path / "shock.jsonl",
            live=True,
        )
        kw = proc.call_args.kwargs
        assert kw["token_by_slug"]["epl-man-united-win-2025-04-01"] == "token-yes-123"
        assert proc.call_args.args[1]
