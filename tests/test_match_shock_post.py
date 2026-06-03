"""Tests for match_shock_post gates and dry-run submit."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from world_cup_bot.config import Settings
from world_cup_bot.match_shock import LadderOrder, LadderPlan
from world_cup_bot.match_shock_config import load_match_shock_config
from world_cup_bot.match_shock_post import (
    check_live_post_gates,
    ladder_to_intents,
    submit_ladder,
)


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


def test_ladder_to_intents():
    plan = LadderPlan(
        bucket_key="k",
        pre_price=0.30,
        percentiles_cents={50: 8.0},
        orders=(LadderOrder(50, 0.22, 5.0, 0.1),),
        recovery_target_price=0.26,
    )
    intents = ladder_to_intents(plan, token_id="tok", slug="s", ttl_ms=60_000)
    assert len(intents) == 1
    assert intents[0].limit_price == 0.22


def test_gates_blocked_when_dry_run(settings):
    cfg = load_match_shock_config()
    gate = check_live_post_gates(settings, cfg, test_auth=True)
    assert not gate.allowed


def test_submit_ladder_dry_run(settings):
    cfg = load_match_shock_config()
    plan = LadderPlan(
        bucket_key="k",
        pre_price=0.30,
        percentiles_cents={50: 8.0},
        orders=(LadderOrder(50, 0.22, 5.0, 0.1),),
        recovery_target_price=0.26,
    )
    rows = submit_ladder(
        plan,
        token_id="tok123",
        slug="epl-test",
        settings=settings,
        cfg=cfg,
        dry_run=True,
    )
    assert rows[0]["dry_run"] is True


def test_gates_pass_when_live(monkeypatch, settings):
    live_settings = Settings(
        gamma_url=settings.gamma_url,
        clob_url=settings.clob_url,
        ws_user_url=settings.ws_user_url,
        ws_market_url=settings.ws_market_url,
        data_api_url=settings.data_api_url,
        match_shock_tape_dir=settings.match_shock_tape_dir,
        match_shock_ledger_path=settings.match_shock_ledger_path,
        dry_run=False,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
        max_notional_per_market_usd=settings.max_notional_per_market_usd,
        conviction_config=settings.conviction_config,
        logic_version_config=settings.logic_version_config,
        ledger_path=settings.ledger_path,
        operating_config=settings.operating_config,
        cross_venue_config=settings.cross_venue_config,
        kalshi_base_url=settings.kalshi_base_url,
        market_phases_config=settings.market_phases_config,
    )
    monkeypatch.setenv("WC_SHOCK_ENABLED", "1")
    monkeypatch.setenv("WC_MATCH_SHOCK_LIVE", "1")
    monkeypatch.setenv("WC_MATCH_SHOCK_LIVE_ACK", "1")
    live_cfg = load_match_shock_config()
    with patch("world_cup_bot.match_shock_config.load_match_shock_config") as mock_cfg:
        import dataclasses

        mock_cfg.return_value = dataclasses.replace(live_cfg, enabled=True)
        with patch("world_cup_bot.match_shock_post.run_preflight") as mock_pf:
            mock_pf.return_value = MagicMock(ok=True, checks=[])
            gate = check_live_post_gates(live_settings, mock_cfg.return_value, test_auth=True)
    assert gate.allowed
