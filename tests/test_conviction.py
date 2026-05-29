from market_helpers import make_market
from world_cup_bot import conviction
from world_cup_bot.conviction import TeamMode, load_conviction_config


def test_load_default_config():
    cfg = load_conviction_config()
    assert cfg.team_mode("Turkey") == TeamMode.YES_HEAVY
    assert cfg.team_mode("Spain") == TeamMode.BILATERAL_ONLY
    assert cfg.team_mode("Mexico") == TeamMode.FADE_WATCH
    assert cfg.team_mode("USA") == TeamMode.SKIP


def test_yes_heavy_mid_band_quotes():
    cfg = load_conviction_config()
    m = make_market("Turkey", mid=0.45)
    result = conviction.evaluate_market(m, cfg)
    assert result.quote
    assert result.mode == TeamMode.YES_HEAVY


def test_yes_heavy_outside_band_skipped():
    cfg = load_conviction_config()
    m = make_market("Turkey", mid=0.15)
    result = conviction.evaluate_market(m, cfg)
    assert not result.quote


def test_bilateral_only_low_mid_skipped():
    cfg = load_conviction_config()
    m = make_market("Spain", mid=0.75)
    result = conviction.evaluate_market(m, cfg)
    assert not result.quote


def test_bilateral_high_mid_quotes():
    cfg = load_conviction_config()
    m = make_market("Spain", mid=0.93, bilateral=True)
    result = conviction.evaluate_market(m, cfg)
    assert result.quote
    assert result.mode == TeamMode.BILATERAL_ONLY


def test_fade_watch_never_quotes():
    cfg = load_conviction_config()
    m = make_market("Mexico", mid=0.83)
    result = conviction.evaluate_market(m, cfg)
    assert result.mode == TeamMode.FADE_WATCH
    assert not result.quote


def test_unknown_kickoff_skipped():
    cfg = load_conviction_config()
    m = make_market("Turkey", mid=0.45, hours_to_kickoff=None)
    result = conviction.evaluate_market(m, cfg)
    assert not result.quote
    assert "fail closed" in result.reason


def test_missing_rewards_skipped():
    cfg = load_conviction_config()
    m = make_market("Turkey", mid=0.45, rewards_max_spread=None)
    result = conviction.evaluate_market(m, cfg)
    assert not result.quote
    assert "reward params" in result.reason


def test_filter_quote_only():
    cfg = load_conviction_config()
    markets = [
        make_market("Turkey", mid=0.45),
        make_market("Mexico", mid=0.83),
        make_market("South Korea", mid=0.67),
    ]
    quoted = conviction.filter_conviction_markets(markets, cfg, quote_only=True)
    assert len(quoted) == 1
    assert quoted[0].market.team == "Turkey"
