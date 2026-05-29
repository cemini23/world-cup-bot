from world_cup_bot import conviction, scanner
from world_cup_bot.conviction import TeamMode, load_conviction_config


def _market(
    team: str,
    *,
    mid: float,
    lp_eligible: bool = True,
    bilateral: bool = False,
) -> scanner.AdvanceMarket:
    return scanner.AdvanceMarket(
        team=team,
        question=f"Will {team} advance to the knockout stages at the 2026 FIFA World Cup?",
        slug=team.lower(),
        condition_id="0x1",
        yes_token_id="yes",
        no_token_id="no",
        best_bid=mid - 0.02,
        best_ask=mid + 0.02,
        spread=0.04,
        mid=mid,
        rewards_min_shares=50.0,
        rewards_max_spread=4.5,
        liquidity=5000.0,
        volume=1000.0,
        accepting_orders=True,
        hours_to_kickoff=48.0,
        must_cancel=False,
        bilateral_mode=bilateral or mid > 0.90,
    )


def test_load_default_config():
    cfg = load_conviction_config()
    assert cfg.team_mode("Turkey") == TeamMode.YES_HEAVY
    assert cfg.team_mode("Spain") == TeamMode.BILATERAL_ONLY
    assert cfg.team_mode("Mexico") == TeamMode.FADE_WATCH
    assert cfg.team_mode("USA") == TeamMode.SKIP


def test_yes_heavy_mid_band_quotes():
    cfg = load_conviction_config()
    m = _market("Turkey", mid=0.45)
    result = conviction.evaluate_market(m, cfg)
    assert result.quote
    assert result.mode == TeamMode.YES_HEAVY


def test_yes_heavy_outside_band_skipped():
    cfg = load_conviction_config()
    m = _market("Turkey", mid=0.15)
    result = conviction.evaluate_market(m, cfg)
    assert not result.quote


def test_bilateral_only_low_mid_skipped():
    cfg = load_conviction_config()
    m = _market("Spain", mid=0.75)
    result = conviction.evaluate_market(m, cfg)
    assert not result.quote


def test_bilateral_high_mid_quotes():
    cfg = load_conviction_config()
    m = _market("Spain", mid=0.93, bilateral=True)
    result = conviction.evaluate_market(m, cfg)
    assert result.quote
    assert result.mode == TeamMode.BILATERAL_ONLY


def test_fade_watch_never_quotes():
    cfg = load_conviction_config()
    m = _market("Mexico", mid=0.83)
    result = conviction.evaluate_market(m, cfg)
    assert result.mode == TeamMode.FADE_WATCH
    assert not result.quote


def test_filter_quote_only():
    cfg = load_conviction_config()
    markets = [
        _market("Turkey", mid=0.45),
        _market("Mexico", mid=0.83),
        _market("South Korea", mid=0.67),
    ]
    quoted = conviction.filter_conviction_markets(markets, cfg, quote_only=True)
    assert len(quoted) == 1
    assert quoted[0].market.team == "Turkey"
