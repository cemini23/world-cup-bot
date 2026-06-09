from dataclasses import replace

import pytest

from market_helpers import make_market
from world_cup_bot import conviction, quoter
from world_cup_bot.config import Settings
from world_cup_bot.conviction import TeamMode, load_conviction_config
from world_cup_bot.quoter import MarketSnapshot


def _settings(**overrides) -> Settings:
    base = dict(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://ws-subscriptions-clob.polymarket.com/ws/user",
        ws_market_url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
        data_api_url="https://data-api.polymarket.com",
        match_shock_tape_dir="data/local/shock_tapes",
        match_shock_ledger_path="data/local/match_shock_paper.jsonl",
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path="data/local/ledger.jsonl",
        operating_config="config/operating.yaml",
        cross_venue_config="config/cross_venue.yaml",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
        market_phases_config="config/market_phases.yaml",
    )
    base.update(overrides)
    return Settings(**base)


def test_yes_heavy_single_leg():
    cfg = load_conviction_config()
    settings = _settings()
    m = make_market("Turkey", mid=0.45)
    result = conviction.evaluate_market(m, cfg)
    intents = quoter.build_quotes(result, cfg, settings)
    assert len(intents) == 1
    assert intents[0].side == "YES"
    assert intents[0].price == pytest.approx(0.43)
    assert intents[0].size_shares >= 500.0
    assert intents[0].dry_run is True
    assert intents[0].order_id.startswith("dry-turkey-yes-")


def test_env_max_notional_caps_yaml_per_team():
    cfg = load_conviction_config()
    settings = _settings(max_notional_per_market_usd=500.0)
    m = make_market("Spain", mid=0.93, bilateral=True)
    result = conviction.ConvictionResult(
        m, TeamMode.BILATERAL_ONLY, True, "bilateral_only high mid"
    )
    intents = quoter.build_quotes(result, cfg, settings)
    assert len(intents) == 2
    total = sum(i.notional_usd for i in intents)
    assert total <= 500.0 + 0.01


def test_bilateral_two_legs():
    cfg = load_conviction_config()
    settings = _settings()
    m = make_market("Spain", mid=0.93, bilateral=True)
    result = conviction.ConvictionResult(
        m, TeamMode.BILATERAL_ONLY, True, "bilateral_only high mid"
    )
    intents = quoter.build_quotes(result, cfg, settings)
    assert len(intents) == 2
    assert {i.side for i in intents} == {"YES", "NO"}


def test_spread_clamp_within_rewards_max():
    cfg = load_conviction_config()
    settings = _settings()
    m = make_market("Turkey", mid=0.50, rewards_max_spread=4.0)
    m = replace(m, best_bid=0.40)
    result = conviction.evaluate_market(m, cfg)
    intents = quoter.build_quotes(result, cfg, settings)
    assert len(intents) == 1
    assert intents[0].price >= 0.46


def test_submit_dry_run_returns_intents():
    settings = _settings()
    snap = MarketSnapshot(
        mid=0.45,
        best_bid=0.43,
        best_ask=0.47,
        spread=0.04,
        rewards_min_shares=500,
        rewards_max_spread=4.5,
        hours_to_kickoff=48.0,
    )
    intent = quoter.QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="111",
        order_id="dry-turkey-yes-abcd1234",
        price=0.44,
        size_shares=100.0,
        notional_usd=44.0,
        dry_run=True,
        reason="test",
        snapshot=snap,
    )
    out = quoter.submit_quotes([intent], settings)
    assert out == [intent]


def test_submit_live_requires_clob_client(monkeypatch):
    settings = _settings(dry_run=False)
    snap = MarketSnapshot(
        mid=0.45,
        best_bid=0.43,
        best_ask=0.47,
        spread=0.04,
        rewards_min_shares=500,
        rewards_max_spread=4.5,
        hours_to_kickoff=48.0,
    )
    intent = quoter.QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="111",
        order_id="live-turkey-yes-abcd1234",
        price=0.44,
        size_shares=100.0,
        notional_usd=44.0,
        dry_run=False,
        reason="test",
        snapshot=snap,
    )

    from world_cup_bot.clob_live import LiveClobNotConfiguredError

    def fake_build(_settings):
        raise LiveClobNotConfiguredError("missing")

    monkeypatch.setattr("world_cup_bot.clob_live.build_clob_client", fake_build)
    monkeypatch.setattr("world_cup_bot.preflight.assert_live_post_allowed", lambda _s: None)
    with pytest.raises(LiveClobNotConfiguredError):
        quoter.submit_quotes([intent], settings)


def test_submit_live_skips_crosses_book(monkeypatch):
    settings = _settings(dry_run=False)
    snap = MarketSnapshot(
        mid=0.45,
        best_bid=0.43,
        best_ask=0.47,
        spread=0.04,
        rewards_min_shares=500,
        rewards_max_spread=4.5,
        hours_to_kickoff=48.0,
    )
    ok = quoter.QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="111",
        order_id="live-turkey-yes-abcd1234",
        price=0.44,
        size_shares=100.0,
        notional_usd=44.0,
        dry_run=False,
        reason="test",
        snapshot=snap,
    )
    bad = quoter.QuoteIntent(
        team="Portugal",
        side="NO",
        token_id="222",
        order_id="live-portugal-no-abcd1234",
        price=0.36,
        size_shares=100.0,
        notional_usd=36.0,
        dry_run=False,
        reason="test",
        snapshot=snap,
    )

    from world_cup_bot.clob_live import LiveClobPostError

    def fake_post(_client, intent):
        if intent.team == "Portugal":
            raise LiveClobPostError("invalid post-only order: order crosses book")

    monkeypatch.setattr("world_cup_bot.clob_live.build_clob_client", lambda _s: object())
    monkeypatch.setattr("world_cup_bot.clob_live.post_quote_intent", fake_post)
    monkeypatch.setattr("world_cup_bot.preflight.assert_live_post_allowed", lambda _s: None)
    out = quoter.submit_quotes([ok, bad], settings)
    assert out == [ok]
