"""Tests for Module 6 cross-venue scanner."""

from __future__ import annotations

import pytest

from world_cup_bot.cross_venue_config import (
    CrossVenueConfig,
    CrossVenuePair,
    DiscoveryConfig,
    load_cross_venue_config,
)
from world_cup_bot.cross_venue_scanner import (
    discover_candidate_pairs,
    gap_pp,
    scan_config_pair,
)
from world_cup_bot.kalshi_rest import KalshiMarketSnapshot, parse_kalshi_market
from world_cup_bot.pm_discovery import (
    PolymarketSnapshot,
    index_polymarket_markets,
    parse_group_winner_market,
)


def _sample_config() -> CrossVenueConfig:
    return CrossVenueConfig(
        version=1,
        alert_threshold_pp=5.0,
        alert_min_fee_adjusted_gap_pp=0.5,
        poll_interval_sec=120,
        fee_kalshi_profit_pct=7.0,
        verification_max_age_days=14,
        pairs=(
            CrossVenuePair(
                team="USA",
                market_type="group_winner",
                polymarket_hint="Will USA win Group D?",
                kalshi_event_ticker="KXWCGROUPWIN-26D",
                kalshi_market_ticker="KXWCGROUPWIN-26D-USA",
                rules_hash="group_winner_fifa_tiebreak_v1",
                enabled=True,
                last_verified="2026-05-29",
                notes=None,
                polymarket_slug="usa-win-group-d",
                polymarket_condition_id="0xabc",
            ),
        ),
        blockers=("test blocker",),
        discovery=DiscoveryConfig(
            kalshi_ticker_prefixes=("KXWCGROUPWIN",),
            polymarket_search_queries=("world cup group winner",),
            rules_hash_by_market_type={"group_winner": "group_winner_fifa_tiebreak_v1"},
            blocked_market_types=frozenset({"group_qualify"}),
        ),
    )


def test_gap_pp():
    assert gap_pp(0.70, 0.64) == pytest.approx(6.0)
    assert gap_pp(None, 0.5) is None


def test_alert_fires_at_six_pp():
    pair = _sample_config().pairs[0]
    pm = PolymarketSnapshot(
        team="USA",
        market_type="group_winner",
        group="D",
        question="Will USA win Group D?",
        slug="usa-win-group-d-new",
        condition_id="0xabc",
        mid=0.70,
        best_bid=0.69,
        best_ask=0.71,
        volume=1000,
        liquidity=5000,
        accepting_orders=True,
    )
    kalshi = KalshiMarketSnapshot(
        ticker="KXWCGROUPWIN-26D-USA",
        event_ticker="KXWCGROUPWIN-26D",
        title="USA wins Group D",
        team="USA",
        market_type="group_winner",
        mid=0.64,
        yes_bid=0.63,
        yes_ask=0.65,
        volume=500,
        volume_24h=100,
        open_interest=50,
        status="open",
    )
    row = scan_config_pair(pair, _sample_config(), pm=pm, kalshi=kalshi)
    assert row.alert is True
    assert row.gap_pp == pytest.approx(6.0)
    assert row.fee_adjusted_gap_pp == pytest.approx(1.1)


def test_alert_suppressed_when_fee_adjusted_below_min():
    pair = CrossVenuePair(
        team="USA",
        market_type="group_qualify",
        polymarket_hint="USA R32",
        kalshi_event_ticker="KXWCGROUPQUAL-26D",
        kalshi_market_ticker="KXWCGROUPQUAL-26D-USA",
        rules_hash="group_qualify_v1",
        enabled=True,
        last_verified="2026-06-05",
        notes=None,
    )
    pm = PolymarketSnapshot(
        team="USA",
        market_type="group_qualify",
        group="D",
        question="Will the United States reach the Round of 32?",
        slug="usa-r32",
        condition_id="0xusa",
        mid=0.82,
        best_bid=0.81,
        best_ask=0.83,
        volume=1000,
        liquidity=5000,
        accepting_orders=True,
    )
    kalshi = KalshiMarketSnapshot(
        ticker="KXWCGROUPQUAL-26D-USA",
        event_ticker="KXWCGROUPQUAL-26D",
        title="USA qualifies",
        team="USA",
        market_type="group_qualify",
        mid=0.86,
        yes_bid=0.85,
        yes_ask=0.87,
        volume=500,
        volume_24h=100,
        open_interest=50,
        status="open",
    )
    row = scan_config_pair(pair, _sample_config(), pm=pm, kalshi=kalshi)
    assert row.gap_pp == pytest.approx(4.0)
    assert row.fee_adjusted_gap_pp == pytest.approx(-2.02)
    assert row.alert is False
    assert row.blocked is False


def test_group_qualify_config_pair_not_blocked_by_discovery_blocklist():
    pair = CrossVenuePair(
        team="England",
        market_type="group_qualify",
        polymarket_hint="England R32",
        kalshi_event_ticker="KXWCGROUPQUAL-26L",
        kalshi_market_ticker="KXWCGROUPQUAL-26L-ENG",
        rules_hash="group_qualify_v1",
        enabled=True,
        last_verified="2026-06-05",
        notes=None,
    )
    row = scan_config_pair(pair, _sample_config(), pm=None, kalshi=None)
    assert row.blocked is False


def test_slug_change_detected():
    pair = _sample_config().pairs[0]
    pm = PolymarketSnapshot(
        team="USA",
        market_type="group_winner",
        group="D",
        question="Will USA win Group D?",
        slug="totally-new-slug",
        condition_id="0xabc",
        mid=0.50,
        best_bid=0.49,
        best_ask=0.51,
        volume=100,
        liquidity=100,
        accepting_orders=True,
    )
    row = scan_config_pair(pair, _sample_config(), pm=pm, kalshi=None)
    assert row.slug_changed is True
    assert "totally-new-slug" in (row.slug_change_detail or "")


def test_stale_last_verified_blocks_alert():
    cfg = _sample_config()
    pair = CrossVenuePair(
        team="USA",
        market_type="group_winner",
        polymarket_hint="Will USA win Group D?",
        kalshi_event_ticker="KXWCGROUPWIN-26D",
        kalshi_market_ticker="KXWCGROUPWIN-26D-USA",
        rules_hash="group_winner_fifa_tiebreak_v1",
        enabled=True,
        last_verified="2026-01-01",
        notes=None,
        polymarket_slug="usa-win-group-d",
        polymarket_condition_id="0xabc",
    )
    pm = PolymarketSnapshot(
        team="USA",
        market_type="group_winner",
        group="D",
        question="Will USA win Group D?",
        slug="usa-win-group-d",
        condition_id="0xabc",
        mid=0.70,
        best_bid=0.69,
        best_ask=0.71,
        volume=1000,
        liquidity=5000,
        accepting_orders=True,
    )
    kalshi = KalshiMarketSnapshot(
        ticker="KXWCGROUPWIN-26D-USA",
        event_ticker="KXWCGROUPWIN-26D",
        title="USA wins Group D",
        team="USA",
        market_type="group_winner",
        mid=0.55,
        yes_bid=0.54,
        yes_ask=0.56,
        volume=500,
        volume_24h=500,
        open_interest=50,
        status="open",
    )
    row = scan_config_pair(pair, cfg, pm=pm, kalshi=kalshi)
    assert row.blocked is True
    assert row.block_reason is not None
    assert "stale" in row.block_reason
    assert row.alert is False


def test_blocked_market_type_no_alert():
    cfg = _sample_config()
    pair = CrossVenuePair(
        team="USA",
        market_type="group_qualify",
        polymarket_hint="",
        kalshi_event_ticker="KXWCGROUPQUAL-26D",
        kalshi_market_ticker="KXWCGROUPQUAL-26D-USA",
        rules_hash="group_qualify_v1",
        enabled=True,
        last_verified=None,
        notes=None,
    )
    pm = PolymarketSnapshot(
        team="USA",
        market_type="group_qualify",
        group="D",
        question="Will USA qualify?",
        slug="x",
        condition_id="1",
        mid=0.80,
        best_bid=0.79,
        best_ask=0.81,
        volume=1,
        liquidity=1,
        accepting_orders=True,
    )
    kalshi = KalshiMarketSnapshot(
        ticker="KXWCGROUPQUAL-26D-USA",
        event_ticker="KXWCGROUPQUAL-26D",
        title="USA qualify",
        team="USA",
        market_type="group_qualify",
        mid=0.70,
        yes_bid=0.69,
        yes_ask=0.71,
        volume=1,
        volume_24h=1,
        open_interest=1,
        status="open",
    )
    row = scan_config_pair(pair, cfg, pm=pm, kalshi=kalshi)
    assert row.blocked is True
    assert row.alert is False


def test_parse_group_winner_market_fifa_wording():
    raw = {
        "question": "Will USA win Group D in the 2026 FIFA World Cup?",
        "slug": "usa-group-d",
        "conditionId": "0x9",
        "bestBid": 0.40,
        "bestAsk": 0.42,
        "acceptingOrders": True,
    }
    parsed = parse_group_winner_market(raw)
    assert parsed is not None
    assert parsed.team == "USA"
    assert parsed.group == "D"


def test_parse_group_winner_market():
    raw = {
        "question": "Will Switzerland win Group B?",
        "slug": "sui-group-b",
        "conditionId": "0x2",
        "bestBid": 0.40,
        "bestAsk": 0.44,
        "acceptingOrders": True,
    }
    parsed = parse_group_winner_market(raw)
    assert parsed is not None
    assert parsed.team == "Switzerland"
    assert parsed.group == "B"
    assert parsed.mid == pytest.approx(0.42)


def test_kalshi_implied_mid_dollars():
    raw = {
        "ticker": "KXWCGROUPWIN-26B-SUI",
        "event_ticker": "KXWCGROUPWIN-26B",
        "title": "Switzerland Group B winner",
        "yes_bid_dollars": "0.3800",
        "yes_ask_dollars": "0.4200",
        "status": "open",
    }
    snap = parse_kalshi_market(raw)
    assert snap.team == "Switzerland"
    assert snap.mid == 0.40


def test_discover_candidate_pairs():
    cfg = _sample_config()
    pm = [
        PolymarketSnapshot(
            team="Mexico",
            market_type="group_winner",
            group="A",
            question="Will Mexico win Group A?",
            slug="mex-a",
            condition_id="0x3",
            mid=0.55,
            best_bid=0.54,
            best_ask=0.56,
            volume=1,
            liquidity=1,
            accepting_orders=True,
        )
    ]
    kalshi = [
        KalshiMarketSnapshot(
            ticker="KXWCGROUPWIN-26A-MEX",
            event_ticker="KXWCGROUPWIN-26A",
            title="Mexico Group A",
            team="Mexico",
            market_type="group_winner",
            mid=0.55,
            yes_bid=0.54,
            yes_ask=0.56,
            volume=1,
            volume_24h=1,
            open_interest=1,
            status="open",
        )
    ]
    proposals = discover_candidate_pairs(cfg, pm_markets=pm, kalshi_markets=kalshi)
    assert len(proposals) == 1
    assert proposals[0].team == "Mexico"
    assert proposals[0].in_config is False


def test_match_polymarket_prefers_config_slug():
    from world_cup_bot.pm_discovery import index_polymarket_by_slug, match_polymarket_for_pair

    stub = PolymarketSnapshot(
        team="England",
        market_type="group_winner",
        group="C",
        question="Will England win Group C?",
        slug="will-england-win-group-c",
        condition_id="0xstub",
        mid=0.5,
        best_bid=0.49,
        best_ask=0.51,
        volume=1,
        liquidity=1,
        accepting_orders=True,
    )
    fifa = PolymarketSnapshot(
        team="England",
        market_type="group_winner",
        group="L",
        question="Will England win Group L in the 2026 FIFA World Cup?",
        slug="will-england-win-group-l-in-the-2026-fifa-world-cup",
        condition_id="0xfifa",
        mid=0.705,
        best_bid=0.69,
        best_ask=0.72,
        volume=1000,
        liquidity=5000,
        accepting_orders=True,
    )
    markets = [stub, fifa]
    catalog = index_polymarket_markets(markets)
    slug_index = index_polymarket_by_slug(markets)
    matched = match_polymarket_for_pair(
        team="England",
        market_type="group_winner",
        hint=fifa.question,
        catalog=catalog,
        markets=markets,
        polymarket_slug=fifa.slug,
        slug_index=slug_index,
    )
    assert matched is not None
    assert matched.slug == fifa.slug
    assert matched.mid == pytest.approx(0.705)


def test_group_qualify_matches_pm_advance_to_knockout():
    from world_cup_bot.pm_discovery import index_polymarket_markets, match_polymarket_for_pair

    pm = PolymarketSnapshot(
        team="USA",
        market_type="advance_to_knockout",
        group=None,
        question="Will USA advance to the knockout stages at the 2026 FIFA World Cup",
        slug="usa-advance",
        condition_id="0xusa-adv",
        mid=0.82,
        best_bid=0.81,
        best_ask=0.83,
        volume=1000,
        liquidity=5000,
        accepting_orders=True,
    )
    catalog = index_polymarket_markets([pm])
    matched = match_polymarket_for_pair(
        team="USA",
        market_type="group_qualify",
        hint="Will USA advance to the knockout stages at the 2026 FIFA World Cup",
        catalog=catalog,
        markets=[pm],
    )
    assert matched is not None
    assert matched.mid == pytest.approx(0.82)


def test_load_cross_venue_config_from_disk():
    cfg = load_cross_venue_config()
    assert cfg.alert_threshold_pp == 5.0
    assert len(cfg.pairs) >= 15
    assert cfg.discovery.kalshi_ticker_prefixes
    assert "group_winner" in cfg.discovery.rules_hash_by_market_type
