from datetime import UTC, datetime

from world_cup_bot import calendar_guard


def test_parse_kickoff_utc_mexico_opener():
    kt = calendar_guard.parse_kickoff_utc("2026-06-11", "13:00 UTC-6")
    assert kt == datetime(2026, 6, 11, 19, 0, tzinfo=UTC)


def test_must_cancel_inside_window():
    schedule = calendar_guard.build_team_schedule()
    now = datetime(2026, 6, 11, 14, 0, tzinfo=UTC)
    assert calendar_guard.must_cancel_orders(
        "Mexico", min_hours_before_kickoff=10.0, now=now, schedule=schedule
    )


def test_must_not_cancel_outside_window():
    schedule = calendar_guard.build_team_schedule()
    now = datetime(2026, 6, 10, 0, 0, tzinfo=UTC)
    assert not calendar_guard.must_cancel_orders(
        "Mexico", min_hours_before_kickoff=10.0, now=now, schedule=schedule
    )


def test_usa_alias():
    schedule = calendar_guard.build_team_schedule()
    assert calendar_guard.next_kickoff_utc("United States", schedule=schedule) is not None
    assert calendar_guard.next_kickoff_utc("USA", schedule=schedule) is not None
