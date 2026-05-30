from world_cup_bot.operating_config import load_operating_config


def test_operating_defaults():
    cfg = load_operating_config()
    assert cfg.calendar.prefer_hours_before_kickoff == 24.0
    assert cfg.bilateral.high_mid == 0.90
    assert cfg.fill_handler.exit_within_seconds == 60.0
    assert cfg.fill_handler.queue_depletion_usd == 150.0
    assert cfg.fill_handler.vol_cooldown_minutes == 30.0
    assert cfg.liquidity.min_depth_within_reward_spread_usd == 50.0
    assert cfg.liquidity.min_ask_depth_within_reward_spread_usd == 15.0
    assert cfg.liquidity.min_combined_book_depth_usd == 150.0
    assert cfg.liquidity.auto_clear_human_review is True
