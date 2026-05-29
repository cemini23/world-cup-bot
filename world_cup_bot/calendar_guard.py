"""Match calendar guard — cancel LP orders before kickoff (T-6h / T-10h rule)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from world_cup_bot import team_names

_PLACEHOLDER = re.compile(r"^(W|L)\d+$|^\d[A-L]$|^.*/.*$")
_KICKOFF = re.compile(r"^(\d{2}):(\d{2}) UTC([+-]?\d+)$")

DEFAULT_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "worldcup2026-fixtures.json"


def parse_kickoff_utc(date_str: str, time_str: str) -> datetime:
    """Parse openfootball date + time (e.g. ``2026-06-11`` + ``13:00 UTC-6``) → UTC."""
    m = _KICKOFF.match(time_str.strip())
    if not m:
        raise ValueError(f"unparseable kickoff time: {time_str!r}")
    hour, minute, offset_hours = int(m.group(1)), int(m.group(2)), int(m.group(3))
    tz = timezone(timedelta(hours=offset_hours))
    local = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=hour, minute=minute, tzinfo=tz)
    return local.astimezone(UTC)


def _is_scheduled_team(name: str | None) -> bool:
    if not name or not name.strip():
        return False
    return _PLACEHOLDER.match(name.strip()) is None


def load_fixtures(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_FIXTURES
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def build_team_schedule(
    fixtures: dict[str, Any] | None = None,
    *,
    path: Path | None = None,
) -> dict[str, list[datetime]]:
    """Map each nation → sorted list of kickoff times (UTC)."""
    data = fixtures if fixtures is not None else load_fixtures(path)
    schedule: dict[str, list[datetime]] = {}

    for match in data.get("matches", []):
        t1, t2 = match.get("team1"), match.get("team2")
        if not _is_scheduled_team(t1) or not _is_scheduled_team(t2):
            continue
        kickoff = parse_kickoff_utc(match["date"], match["time"])
        for raw in (t1, t2):
            team = team_names.normalize_team(raw)
            team_names._FIXTURE_CANONICAL.add(team)
            schedule.setdefault(team, []).append(kickoff)

    for team in schedule:
        schedule[team].sort()
    return schedule


def next_kickoff_utc(
    team: str,
    *,
    now: datetime | None = None,
    schedule: dict[str, list[datetime]] | None = None,
    path: Path | None = None,
) -> datetime | None:
    now = now or datetime.now(UTC)
    sched = schedule if schedule is not None else build_team_schedule(path=path)
    canon = team_names.normalize_team(team)
    kickoffs = sched.get(canon)
    if not kickoffs:
        for name, times in sched.items():
            if team_names.teams_match(name, team):
                kickoffs = times
                break
    if not kickoffs:
        return None
    for kt in kickoffs:
        if kt > now:
            return kt
    return None


def hours_until_kickoff(
    team: str,
    *,
    now: datetime | None = None,
    schedule: dict[str, list[datetime]] | None = None,
    path: Path | None = None,
) -> float | None:
    nxt = next_kickoff_utc(team, now=now, schedule=schedule, path=path)
    if nxt is None:
        return None
    now = now or datetime.now(UTC)
    return (nxt - now).total_seconds() / 3600.0


def must_cancel_orders(
    team: str,
    *,
    min_hours_before_kickoff: float = 10.0,
    now: datetime | None = None,
    schedule: dict[str, list[datetime]] | None = None,
    path: Path | None = None,
) -> bool:
    hours = hours_until_kickoff(team, now=now, schedule=schedule, path=path)
    if hours is None:
        return False
    return hours < min_hours_before_kickoff


def teams_in_cancel_window(
    *,
    min_hours_before_kickoff: float = 10.0,
    now: datetime | None = None,
    schedule: dict[str, list[datetime]] | None = None,
    path: Path | None = None,
) -> list[tuple[str, float]]:
    now = now or datetime.now(UTC)
    sched = schedule if schedule is not None else build_team_schedule(path=path)
    out: list[tuple[str, float]] = []
    for team in sched:
        hours = hours_until_kickoff(team, now=now, schedule=sched)
        if hours is not None and hours < min_hours_before_kickoff:
            out.append((team, hours))
    out.sort(key=lambda x: x[1])
    return out
