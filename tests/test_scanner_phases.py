"""Tests for multi-phase scanner (Module 1b PR2)."""

from __future__ import annotations

import io
import re
from datetime import UTC, datetime
from pathlib import Path

from world_cup_bot import scanner
from world_cup_bot.market_phases import load_market_phases_config

FIXTURE = Path(__file__).parent / "fixtures" / "gamma_search_sample.json"
CONFIG = Path(__file__).resolve().parents[1] / "config" / "market_phases.yaml"


def _opener(_url: str, timeout: int = 30):
    return io.BytesIO(FIXTURE.read_bytes())


def test_build_scan_targets_from_config():
    cfg = load_market_phases_config(CONFIG)
    targets = scanner.build_scan_targets(cfg, ["group_advance", "reach_round_of_16"])
    assert len(targets) == 2
    assert targets[0].phase_id == "group_advance"


def test_parse_team_with_reach_pattern():
    cfg = load_market_phases_config(CONFIG)
    spec = cfg.phases["reach_round_of_16"]
    pattern = re.compile(spec.title_regex, re.IGNORECASE)
    team = scanner.parse_team_with_pattern(
        "Will Brazil reach the Round of 16 at the 2026 FIFA World Cup?",
        pattern,
    )
    assert team == "Brazil"


def test_discover_markets_multi_phase_uses_fixture():
    cfg = load_market_phases_config(CONFIG)
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    markets = scanner.discover_markets(
        "https://gamma-api.polymarket.com",
        now=now,
        opener=_opener,
        phase_ids=["group_advance"],
        phases_config=cfg,
    )
    assert len(markets) == 2
    assert all(m.market_phase_id == "group_advance" for m in markets)
