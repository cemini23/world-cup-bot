"""Tests for deep research mode bundles."""

from unittest.mock import patch

from market_helpers import make_market
from world_cup_bot.config import Settings
from world_cup_bot.cross_venue_scanner import CrossVenueScanResult
from world_cup_bot.research import (
    ResearchMode,
    build_gemini_deep_research_prompt,
    build_research_bundle,
    list_research_modes,
    teams_in_group,
)


def _settings() -> Settings:
    return Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://example/ws/user",
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


def test_list_research_modes():
    modes = list_research_modes()
    assert len(modes) == len(ResearchMode)
    assert any(m["mode"] == "group-conviction" for m in modes)


def test_teams_in_group_b():
    teams = teams_in_group("B")
    assert "Canada" in teams
    assert "Qatar" in teams
    assert len(teams) == 4


def test_build_group_conviction_bundle():
    markets = [
        make_market("Canada", mid=0.52),
        make_market("Switzerland", mid=0.88, bilateral=True),
    ]
    with patch("world_cup_bot.research.scanner.discover_advance_markets", return_value=markets):
        bundle = build_research_bundle(ResearchMode.GROUP_CONVICTION, _settings(), group="B")
    assert bundle.mode == "group-conviction"
    assert bundle.focus["group"] == "B"
    assert "Canada" in bundle.focus["fixture_teams"]
    assert len(bundle.instructions) > 100


def test_build_module6_scanner_bundle():
    with patch("world_cup_bot.research.scanner.discover_advance_markets", return_value=[]):
        bundle = build_research_bundle(ResearchMode.MODULE6_SCANNER, _settings())
    assert bundle.focus["implementation_status"] == "built"
    assert bundle.focus["config_pairs"] >= 15
    assert "cross-venue-scan" in bundle.focus["cli"]


def _empty_cross_venue_scan() -> CrossVenueScanResult:
    return CrossVenueScanResult(
        scanned_at="2026-06-03T00:00:00+00:00",
        config_version=1,
        alert_threshold_pp=5.0,
        blockers=(),
        rows=(),
        discoveries=(),
        pm_market_count=0,
        kalshi_market_count=0,
    )


def test_build_cross_venue_bundle():
    markets = [make_market("USA", mid=0.70)]
    with (
        patch("world_cup_bot.research.scanner.discover_advance_markets", return_value=markets),
        patch(
            "world_cup_bot.research.cross_venue_scanner.run_scan",
            return_value=_empty_cross_venue_scan(),
        ),
    ):
        bundle = build_research_bundle(ResearchMode.CROSS_VENUE, _settings())
    assert "fade_watch_teams" in bundle.focus
    assert "USA" in bundle.focus["fade_watch_teams"]
    assert bundle.focus["live_cross_venue_alerts"] == []


def test_build_gemini_prompt_group():
    markets = [make_market("Canada", mid=0.52)]
    with patch("world_cup_bot.research.scanner.discover_advance_markets", return_value=markets):
        text = build_gemini_deep_research_prompt(
            ResearchMode.GROUP_CONVICTION, _settings(), group="B"
        )
    assert "Group B" in text
    assert "Canada" in text
    assert "{{BOT_CONTEXT}}" not in text
    assert "{{GROUP}}" not in text


def test_build_gemini_prompt_team():
    markets = [make_market("Turkey", mid=0.45)]
    with patch("world_cup_bot.research.scanner.discover_advance_markets", return_value=markets):
        text = build_gemini_deep_research_prompt(
            ResearchMode.TEAM_LP_RISK, _settings(), team="Turkey"
        )
    assert "Turkey" in text
    assert "lp_posture" in text or "LP safety" in text


def test_team_lp_risk_requires_team():
    try:
        build_research_bundle(ResearchMode.TEAM_LP_RISK, _settings())
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "team" in str(exc).lower()
