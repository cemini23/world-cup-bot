"""K109 semantic blocklist tests."""

from __future__ import annotations

from world_cup_bot.cross_venue_semantic import load_semantic_rules


def test_rej_02_reach_r16_vs_groupqual():
    rules = load_semantic_rules()
    hit = rules.check(
        pm_slug="will-england-reach-the-round-of-16",
        kalshi_ticker="KXWCGROUPQUAL-26L-ENG",
        pm_market_type="round_of_16_qualify",
    )
    assert hit is not None
    assert hit[0] == "REJ_02"


def test_rej_03_group_winner_vs_groupqual():
    rules = load_semantic_rules()
    hit = rules.check(
        pm_slug="will-usa-win-group-d-in-the-2026-fifa-world-cup",
        kalshi_ticker="KXWCGROUPQUAL-26D-USA",
        pm_market_type="group_winner",
    )
    assert hit is not None
    assert hit[0] == "REJ_03"


def test_group_winner_vs_groupwin_not_blocked():
    rules = load_semantic_rules()
    hit = rules.check(
        pm_slug="will-usa-win-group-d-in-the-2026-fifa-world-cup",
        kalshi_ticker="KXWCGROUPWIN-26D-USA",
        pm_market_type="group_winner",
    )
    assert hit is None


def test_macro_unhedged_prefix():
    rules = load_semantic_rules()
    assert rules.is_macro_unhedged("KXWCHOSTKO-26-USA")
