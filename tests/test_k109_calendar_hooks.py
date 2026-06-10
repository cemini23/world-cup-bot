"""K109 calendar hook tests."""

from __future__ import annotations

from datetime import UTC, datetime

from world_cup_bot.k109_calendar_hooks import (
    calendar_hook_payload,
    is_final_group_day,
    match_market_mapping_allowed,
    third_place_live_hook,
)


def test_final_group_day():
    assert is_final_group_day(datetime(2026, 6, 27, 12, 0, tzinfo=UTC))
    assert not is_final_group_day(datetime(2026, 6, 26, 12, 0, tzinfo=UTC))


def test_third_place_hook_on_final_day():
    hook = third_place_live_hook(now=datetime(2026, 6, 27, 18, 0, tzinfo=UTC))
    assert hook is not None
    assert hook["hook"] == "third_place_live_state"
    assert len(hook["third_place_candidates"]) > 0


def test_match_market_90min_allowed_in_knockout():
    ok, reason = match_market_mapping_allowed(
        pm_question="Who wins after 90 minutes of regular play?",
        pm_market_type="match_winner",
        kalshi_ticker="KXWCGAME-26-ENG-USA",
        tournament_phase="round_of_32",
    )
    assert ok
    assert reason is None


def test_match_market_et_blocked_vs_kxwcgame():
    ok, reason = match_market_mapping_allowed(
        pm_question="Will England advance (including extra time and penalties)?",
        pm_market_type="match_winner",
        kalshi_ticker="KXWCGAME-26-ENG-USA",
        tournament_phase="round_of_32",
    )
    assert not ok
    assert reason and "REJ_04" in reason


def test_transition_hook():
    hook = calendar_hook_payload(tournament_phase="group_to_knockout_transition")
    assert hook is not None
    assert hook["hook"] == "group_to_knockout_transition"
