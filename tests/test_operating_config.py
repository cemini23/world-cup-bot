from world_cup_bot.operating_config import load_operating_config


def test_operating_defaults():
    cfg = load_operating_config()
    assert cfg.calendar.prefer_hours_before_kickoff == 24.0
    assert cfg.bilateral.high_mid == 0.90
    assert cfg.fill_handler.exit_within_seconds == 60.0
    assert cfg.fill_handler.queue_depletion_usd == 300.0
