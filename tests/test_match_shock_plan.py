"""Tests for match_shock_plan tape processing."""

from __future__ import annotations

from pathlib import Path

import pytest

from world_cup_bot.config import Settings
from world_cup_bot.match_shock_config import load_match_shock_config
from world_cup_bot.match_shock_plan import process_tape_once, run_plan_once

FIXTURE = Path(__file__).resolve().parents[0] / "fixtures" / "shock_replay" / "sample_trades.jsonl"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://example/ws/user",
        ws_market_url="wss://example/ws/market",
        data_api_url="https://data-api.polymarket.com",
        match_shock_tape_dir=str(tmp_path / "tapes"),
        match_shock_ledger_path=str(tmp_path / "shock.jsonl"),
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path=str(tmp_path / "ledger.jsonl"),
        operating_config="config/operating.yaml",
        cross_venue_config="config/cross_venue.yaml",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
        market_phases_config="config/market_phases.yaml",
    )


def test_process_tape_once(settings, tmp_path):
    cfg = load_match_shock_config()
    ledger = tmp_path / "shock.jsonl"
    stats = process_tape_once(
        FIXTURE,
        markets=[],
        shock_cfg=cfg,
        settings=settings,
        ledger_path=ledger,
    )
    assert stats.slugs_scanned >= 1
    assert ledger.is_file()


def test_run_plan_once_with_tape(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("WC_SHOCK_ENABLED", "1")
    stats = run_plan_once(
        settings,
        tape_path=FIXTURE,
        ledger_path=tmp_path / "shock.jsonl",
        status_path=tmp_path / "status.json",
    )
    assert stats.slugs_scanned >= 1
    assert (tmp_path / "status.json").is_file()


def test_run_plan_once_no_tape_writes_skipped(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("WC_SHOCK_ENABLED", "1")
    status_path = tmp_path / "status.json"
    stats = run_plan_once(
        settings,
        ledger_path=tmp_path / "shock.jsonl",
        status_path=status_path,
    )
    assert stats.errors
    payload = __import__("json").loads(status_path.read_text())
    assert payload["status"] == "skipped"
