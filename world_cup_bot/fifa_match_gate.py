"""FIFA fixture match-count gate — hold knockout FSM until group stage completes (PR3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from world_cup_bot.calendar_guard import load_fixtures, parse_kickoff_utc

DEFAULT_GROUP_MATCHES_48 = 72
MATCH_END_BUFFER = timedelta(minutes=105)


@dataclass(frozen=True)
class FifaMatchGateConfig:
    min_group_matches_to_enter_knockout: int = DEFAULT_GROUP_MATCHES_48
    match_duration_minutes: int = 105

    @classmethod
    def from_market_phases_raw(cls, raw: dict[str, Any] | None) -> FifaMatchGateConfig:
        body = raw or {}
        return cls(
            min_group_matches_to_enter_knockout=int(
                body.get("min_group_matches_to_enter_knockout", DEFAULT_GROUP_MATCHES_48)
            ),
            match_duration_minutes=int(body.get("match_duration_minutes", 105)),
        )


@dataclass(frozen=True)
class FifaMatchGateStatus:
    completed_group_matches: int
    required_group_matches: int
    blocked: bool

    @property
    def satisfied(self) -> bool:
        return self.completed_group_matches >= self.required_group_matches


def is_group_stage_match(match: dict[str, Any]) -> bool:
    round_name = str(match.get("round") or "")
    group = match.get("group")
    return round_name.startswith("Matchday") or (
        isinstance(group, str) and group.startswith("Group")
    )


def count_completed_group_matches(
    *,
    now: datetime,
    fixtures_path: Path | None = None,
    fixtures: dict[str, Any] | None = None,
    match_duration: timedelta = MATCH_END_BUFFER,
) -> int:
    data = fixtures if fixtures is not None else load_fixtures(fixtures_path)
    count = 0
    for match in data.get("matches") or []:
        if not is_group_stage_match(match):
            continue
        try:
            kickoff = parse_kickoff_utc(str(match["date"]), str(match["time"]))
        except (KeyError, ValueError):
            continue
        if now >= kickoff + match_duration:
            count += 1
    return count


def check_fifa_match_gate(
    *,
    calendar_state_id: str,
    gate_config: FifaMatchGateConfig,
    now: datetime,
    fixtures_path: Path | None = None,
    completed_override: int | None = None,
) -> FifaMatchGateStatus:
    completed = (
        completed_override
        if completed_override is not None
        else count_completed_group_matches(now=now, fixtures_path=fixtures_path)
    )
    post_group = {
        "round_of_32",
        "round_of_16",
        "quarterfinal",
        "semifinal",
        "third_place",
        "final",
        "post_tournament",
    }
    blocked = calendar_state_id in post_group and completed < (
        gate_config.min_group_matches_to_enter_knockout
    )
    return FifaMatchGateStatus(
        completed_group_matches=completed,
        required_group_matches=gate_config.min_group_matches_to_enter_knockout,
        blocked=blocked,
    )


def apply_fifa_match_gate(
    calendar_state_id: str,
    gate_status: FifaMatchGateStatus,
    *,
    gate_enabled: bool,
) -> tuple[str, str | None]:
    if not gate_enabled or not gate_status.blocked:
        return calendar_state_id, None
    return "group_to_knockout_transition", "fifa_group_matches"
