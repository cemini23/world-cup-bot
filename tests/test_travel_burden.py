"""Tests for group-stage travel burden sizing."""

from __future__ import annotations

from world_cup_bot.travel_burden import (
    TravelBurdenConfig,
    load_travel_burden_config,
    max_one_way_travel_miles,
    notional_multiplier_from_miles,
    travel_burden_state,
)


def _cfg(**overrides) -> TravelBurdenConfig:
    base = load_travel_burden_config()
    return TravelBurdenConfig(
        enabled=overrides.get("enabled", base.enabled),
        max_notional_penalty_pct=overrides.get(
            "max_notional_penalty_pct", base.max_notional_penalty_pct
        ),
        miles_no_penalty_below=overrides.get("miles_no_penalty_below", base.miles_no_penalty_below),
        miles_full_penalty_at=overrides.get("miles_full_penalty_at", base.miles_full_penalty_at),
    )


def test_mexico_low_travel_no_penalty():
    miles, hub, _ = max_one_way_travel_miles("Mexico")
    assert miles is not None
    assert miles < 400
    state = travel_burden_state("Mexico")
    assert state.notional_multiplier == 1.0
    assert hub == "Mexico City, MX"


def test_turkey_high_travel_slight_penalty():
    miles, _, farthest = max_one_way_travel_miles("Turkey")
    assert miles is not None
    assert miles > 900
    assert farthest == "Vancouver"
    state = travel_burden_state("Turkey")
    assert 0.94 <= state.notional_multiplier < 1.0


def test_croatia_far_flung_base_penalized():
    state = travel_burden_state("Croatia")
    assert state.max_one_way_miles is not None
    assert state.max_one_way_miles > 800
    assert state.notional_multiplier < 1.0


def test_disabled_returns_one():
    state = travel_burden_state("Turkey", _cfg(enabled=False))
    assert state.notional_multiplier == 1.0


def test_unknown_team_no_penalty():
    state = travel_burden_state("Atlantis FC")
    assert state.notional_multiplier == 1.0


def test_multiplier_curve_endpoints():
    cfg = _cfg(
        max_notional_penalty_pct=0.06,
        miles_no_penalty_below=300,
        miles_full_penalty_at=2000,
    )
    assert notional_multiplier_from_miles(200, cfg) == 1.0
    assert notional_multiplier_from_miles(2000, cfg) == 0.94
    mid = notional_multiplier_from_miles(1150, cfg)
    assert 0.94 < mid < 1.0


def test_max_penalty_floor():
    cfg = _cfg(max_notional_penalty_pct=0.06)
    assert notional_multiplier_from_miles(5000, cfg) == 0.94
