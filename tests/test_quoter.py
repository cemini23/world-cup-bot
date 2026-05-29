import pytest

from world_cup_bot import conviction, quoter, scanner
from world_cup_bot.config import Settings
from world_cup_bot.conviction import TeamMode, load_conviction_config


def _market(team: str, *, mid: float, bilateral: bool = False) -> scanner.AdvanceMarket:
    return scanner.AdvanceMarket(
        team=team,
        question=f"Will {team} advance?",
        slug=team.lower(),
        condition_id="0x1",
        yes_token_id="111",
        no_token_id="222",
        best_bid=0.43,
        best_ask=0.47,
        spread=0.04,
        mid=mid,
        rewards_min_shares=50.0,
        rewards_max_spread=4.5,
        liquidity=5000.0,
        volume=1000.0,
        accepting_orders=True,
        hours_to_kickoff=72.0,
        must_cancel=False,
        bilateral_mode=bilateral,
    )


def test_yes_heavy_single_leg():
    cfg = load_conviction_config()
    settings = Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
    )
    m = _market("Turkey", mid=0.45)
    result = conviction.evaluate_market(m, cfg)
    intents = quoter.build_quotes(result, cfg, settings)
    assert len(intents) == 1
    assert intents[0].side == "YES"
    assert intents[0].price == pytest.approx(0.43)
    assert intents[0].size_shares >= 50.0
    assert intents[0].dry_run is True


def test_bilateral_two_legs():
    cfg = load_conviction_config()
    settings = Settings.from_env()
    m = _market("Spain", mid=0.93, bilateral=True)
    result = conviction.ConvictionResult(
        m, TeamMode.BILATERAL_ONLY, True, "bilateral_only high mid"
    )
    intents = quoter.build_quotes(result, cfg, settings)
    assert len(intents) == 2
    sides = {i.side for i in intents}
    assert sides == {"YES", "NO"}


def test_submit_dry_run_returns_intents():
    settings = Settings.from_env()
    intent = quoter.QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="111",
        price=0.44,
        size_shares=100.0,
        notional_usd=44.0,
        dry_run=True,
        reason="test",
    )
    out = quoter.submit_quotes([intent], settings)
    assert out == [intent]


def test_submit_live_raises():
    settings = Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        dry_run=False,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
    )
    intent = quoter.QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="111",
        price=0.44,
        size_shares=100.0,
        notional_usd=44.0,
        dry_run=False,
        reason="test",
    )
    with pytest.raises(NotImplementedError):
        quoter.submit_quotes([intent], settings)
