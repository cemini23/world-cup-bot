"""K109 market registry tests."""

from __future__ import annotations

from world_cup_bot.wc_market_registry import load_wc_market_registry


def test_registry_group_advance_count():
    reg = load_wc_market_registry()
    assert reg.count_group_advance_r32() >= 48
    assert reg.count_kalshi_groupqual_hints() >= 48


def test_lp_excludes_group_winner_phase():
    reg = load_wc_market_registry()
    assert not reg.lp_allowed_for_phase("knockout_match_90min")
    assert reg.lp_allowed_for_phase("group_advance")
