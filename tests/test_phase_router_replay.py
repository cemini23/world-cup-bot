"""Tests for Phase B cross-venue manual fills."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from world_cup_bot import phase_router
from world_cup_bot.fifa_match_gate import (
    FifaMatchGateConfig,
    apply_fifa_match_gate,
    check_fifa_match_gate,
    count_completed_group_matches,
)
from world_cup_bot.operating_config import apply_bilateral_threshold_override, load_operating_config
from world_cup_bot.phase_replay import load_replay_jsonl, run_replay

REPLAY_DIR = Path(__file__).resolve().parent / "fixtures" / "phase_router_replay"


@pytest.fixture
def config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "market_phases.yaml"


@pytest.fixture
def fixtures_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "worldcup2026-fixtures.json"


@pytest.mark.parametrize(
    "fixture_file",
    [
        "wc2026_calendar.jsonl",
        "wc2022_settlement_hold.jsonl",
        "wc2023_knockout_progression.jsonl",
        "wc2026_fifa_match_gate.jsonl",
    ],
)
def test_phase_router_replay_fixtures(config_path: Path, fixture_file: str):
    path = REPLAY_DIR / fixture_file
    steps = load_replay_jsonl(path)
    report = run_replay(config_path, steps, fixture_name=fixture_file)
    failures = [r for r in report.results if not r.passed]
    assert report.ok, "\n".join(r.detail or r.step.label for r in failures)


def test_fifa_match_gate_blocks_knockout(config_path: Path):
    status = check_fifa_match_gate(
        calendar_state_id="round_of_32",
        gate_config=FifaMatchGateConfig(min_group_matches_to_enter_knockout=72),
        now=datetime(2026, 6, 28, tzinfo=UTC),
        completed_override=70,
    )
    assert status.blocked
    hold, blocked_by = apply_fifa_match_gate("round_of_32", status, gate_enabled=True)
    assert hold == "group_to_knockout_transition"
    assert blocked_by == "fifa_group_matches"


def test_fifa_match_gate_allows_when_complete(config_path: Path):
    status = check_fifa_match_gate(
        calendar_state_id="round_of_32",
        gate_config=FifaMatchGateConfig(min_group_matches_to_enter_knockout=72),
        now=datetime(2026, 6, 28, tzinfo=UTC),
        completed_override=72,
    )
    assert status.satisfied
    state, blocked = apply_fifa_match_gate("round_of_32", status, gate_enabled=True)
    assert state == "round_of_32"
    assert blocked is None


def test_count_completed_group_matches(fixtures_path: Path):
    # Before tournament — zero completed group matches
    n = count_completed_group_matches(
        now=datetime(2026, 6, 1, tzinfo=UTC),
        fixtures_path=fixtures_path,
    )
    assert n == 0


def test_bilateral_threshold_override():
    base = load_operating_config()
    merged = apply_bilateral_threshold_override(base, 0.85)
    assert merged.bilateral.high_mid == pytest.approx(0.85)
    assert merged.bilateral.low_mid == pytest.approx(0.15)


def test_quarterfinal_bilateral_in_router(config_path: Path):
    ctx = phase_router.resolve_phase_router(
        config_path,
        now=datetime(2026, 7, 10, tzinfo=UTC),
        enabled=True,
        settlement_gate_enabled=False,
    )
    assert ctx.tournament_phase == "quarterfinal"
    assert ctx.operating_overrides.get("bilateral_threshold") == pytest.approx(0.85)
