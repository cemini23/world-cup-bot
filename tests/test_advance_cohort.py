"""Tests for K107 advance cohort refresh."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from world_cup_bot.advance_cohort import AdvanceCohortRefresh, scan_advance_cohort_refresh
from world_cup_bot.cross_venue_config import (
    CrossVenueConfig,
    CrossVenuePair,
    DiscoveryConfig,
)
from world_cup_bot.pm_discovery import PolymarketSnapshot


def _snap(team: str, slug: str, *, accepting: bool = True) -> PolymarketSnapshot:
    return PolymarketSnapshot(
        team=team,
        market_type="advance_to_knockout",
        group=None,
        question=f"Will {team} advance?",
        slug=slug,
        condition_id=f"cid-{team}",
        mid=0.5,
        best_bid=0.49,
        best_ask=0.51,
        volume=1000.0,
        liquidity=500.0,
        accepting_orders=accepting,
    )


def test_advance_cohort_missing_slugs(tmp_path: Path):
    discovery = DiscoveryConfig(
        kalshi_ticker_prefixes=(),
        polymarket_search_queries=(),
        rules_hash_by_market_type={"advance_to_knockout": "advance_knockout_v1"},
        blocked_market_types=frozenset(),
    )
    cfg = CrossVenueConfig(
        version=1,
        alert_threshold_pp=5.0,
        poll_interval_sec=120,
        fee_kalshi_profit_pct=7.0,
        verification_max_age_days=14,
        pairs=(
            CrossVenuePair(
                team="Brazil",
                market_type="advance_to_knockout",
                polymarket_hint="",
                polymarket_slug="brazil-advance",
                kalshi_event_ticker="E",
                kalshi_market_ticker="M",
                rules_hash="advance_knockout_v1",
                enabled=True,
                last_verified="2026-06-01",
                notes="",
            ),
        ),
        blockers=(),
        discovery=discovery,
        paper_arb=None,
        auto_arb=None,
        alert_min_fee_adjusted_gap_pp=0.5,
    )
    cv_path = tmp_path / "cross_venue.yaml"
    cv_path.write_text("version: 1\npairs: []\n", encoding="utf-8")

    pm_markets = [
        _snap("Brazil", "brazil-advance"),
        _snap("France", "france-advance-new"),
    ]

    with patch(
        "world_cup_bot.advance_cohort.discover_polymarket_markets",
        return_value=pm_markets,
    ):
        with patch(
            "world_cup_bot.advance_cohort.load_cross_venue_config",
            return_value=cfg,
        ):
            refresh = scan_advance_cohort_refresh(
                gamma_url="https://gamma-api.polymarket.com",
                cross_venue_config_path=cv_path,
            )

    assert refresh.needs_refresh is True
    assert "france-advance-new" in refresh.missing_from_config
    assert isinstance(refresh, AdvanceCohortRefresh)
