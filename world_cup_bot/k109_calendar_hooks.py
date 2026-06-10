"""K109 calendar hooks — final group day, third-place state, match-market rules gates."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from world_cup_bot.calendar_guard import load_fixtures
from world_cup_bot.fifa_match_gate import count_completed_group_matches, is_group_stage_match
from world_cup_bot.research import _THIRD_PLACE_CANDIDATES

_FINAL_GROUP_DAY = "2026-06-27"
_KNOCKOUT_PHASES = frozenset(
    {
        "round_of_32",
        "round_of_16",
        "quarterfinal",
        "semifinal",
        "third_place",
        "final",
    }
)

_NINETY_MIN_RE = re.compile(
    r"(90\s*min|ninety\s*min|end of (?:the )?90|regulation time|after 90)",
    re.IGNORECASE,
)
_ET_PENS_RE = re.compile(
    r"(extra time|after extra|penalt(y|ies)|shootout|to advance)",
    re.IGNORECASE,
)


def is_final_group_day(now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    return now.strftime("%Y-%m-%d") == _FINAL_GROUP_DAY


def third_place_live_hook(*, now: datetime | None = None) -> dict[str, Any] | None:
    """Third-place / GD math hook on final group matchday (openfootball fixtures)."""
    now = now or datetime.now(UTC)
    if not is_final_group_day(now):
        return None
    fixtures = load_fixtures()
    completed = count_completed_group_matches(now=now, fixtures=fixtures)
    group_matches_today = sum(
        1
        for m in fixtures.get("matches") or []
        if is_group_stage_match(m) and str(m.get("date")) == _FINAL_GROUP_DAY
    )
    return {
        "event": "k109_calendar_hook",
        "hook": "third_place_live_state",
        "final_group_day": _FINAL_GROUP_DAY,
        "completed_group_matches": completed,
        "group_matches_on_final_day": group_matches_today,
        "third_place_candidates": sorted(_THIRD_PLACE_CANDIDATES),
        "note": "Extend cancel lead; review third-place GD before conviction moves",
    }


def match_market_mapping_allowed(
    *,
    pm_question: str | None,
    pm_market_type: str | None,
    kalshi_ticker: str | None,
    tournament_phase: str | None,
) -> tuple[bool, str | None]:
    """
    Knockout MD1+: require PM rules text for 90-min vs ET/penalties before KXWCGAME pairing.
    Returns (allowed, block_reason).
    """
    ticker = (kalshi_ticker or "").upper()
    if not ticker.startswith("KXWCGAME"):
        return True, None
    phase = (tournament_phase or "").strip()
    if phase not in _KNOCKOUT_PHASES:
        return False, "REJ_04: match LP out of scope pre-knockout (v1)"
    mtype = (pm_market_type or "").lower()
    if mtype not in {"match_winner", "unknown", ""}:
        return True, None
    q = (pm_question or "").strip()
    if not q:
        return False, "REJ_04: PM match without rules text"
    if _NINETY_MIN_RE.search(q):
        return True, None
    if _ET_PENS_RE.search(q):
        return False, "REJ_04: PM advance/ET semantics ≠ Kalshi 90-min KXWCGAME"
    return False, "REJ_04: PM match without 90-min rules tag"


def calendar_hook_payload(
    *,
    tournament_phase: str | None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Emit on plan/scan when calendar windows need operator awareness."""
    now = now or datetime.now(UTC)
    third = third_place_live_hook(now=now)
    if third is not None:
        third["tournament_phase"] = tournament_phase
        return third
    if tournament_phase == "group_to_knockout_transition":
        return {
            "event": "k109_calendar_hook",
            "hook": "group_to_knockout_transition",
            "tournament_phase": tournament_phase,
            "note": "Extended cancel lead (12h); cross-venue disabled until settlement",
        }
    return None
