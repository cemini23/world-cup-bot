"""Shock tape calendar day — Eastern default (fifwc slug dates)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from world_cup_bot.shock_tape import (
    kickoff_slug_dates,
    resolve_shock_tape_path,
    shock_tape_calendar_day,
    shock_tape_tz,
)


def test_shock_tape_calendar_day_uses_eastern_not_utc():
    # 2026-06-13 00:30 UTC is still 2026-06-12 evening in US Eastern
    dt = datetime(2026, 6, 13, 0, 30, tzinfo=ZoneInfo("UTC"))
    assert shock_tape_calendar_day(dt) == "2026-06-12"
    assert shock_tape_tz() == ZoneInfo("America/New_York")


def test_kickoff_slug_dates_from_json(tmp_path: Path):
    kickoff = tmp_path / "kickoff.json"
    kickoff.write_text(
        '{"markets":[{"slug":"fifwc-can-bih-2026-06-12-can"},{"slug":"fifwc-usa-par-2026-06-12-usa"}]}',
        encoding="utf-8",
    )
    assert kickoff_slug_dates(kickoff) == ["2026-06-12"]


def test_resolve_shock_tape_path_prefers_slug_date(tmp_path: Path):
    tape_dir = tmp_path / "tapes"
    tape_dir.mkdir()
    kickoff = tmp_path / "kickoff.json"
    kickoff.write_text(
        '{"markets":[{"slug":"fifwc-can-bih-2026-06-12-can"}]}',
        encoding="utf-8",
    )
    slug_day_file = tape_dir / "2026-06-12.jsonl"
    slug_day_file.write_text('{"slug":"fifwc-can-bih-2026-06-12-can"}\n', encoding="utf-8")
    resolved = resolve_shock_tape_path(tape_dir, kickoff_json=kickoff)
    assert resolved == slug_day_file
