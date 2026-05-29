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
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path="data/local/ledger.jsonl",
        operating_config="config/operating.yaml",
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


def test_submit_live_raises():
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
    with pytest.raises(NotImplementedError):
        quoter.submit_quotes([intent], settings)
