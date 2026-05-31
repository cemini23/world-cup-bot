"""Tests for fill handler (Module 4)."""

from datetime import UTC, datetime, timedelta

from market_helpers import make_market
from world_cup_bot import fill_handler
from world_cup_bot.operating_config import load_operating_config


def _fill(**kwargs) -> fill_handler.FillEvent:
    base = dict(
        order_id="fill-001",
        team="Turkey",
        side="YES",
        token_id="yes-tok",
        fill_price=0.44,
        fill_shares=500.0,
        filled_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )
    base.update(kwargs)
    return fill_handler.FillEvent(**base)


def test_exit_within_60s():
    ops = load_operating_config()
    filled = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    due = fill_handler.exit_due_by(filled, ops.fill_handler)
    assert due - filled == timedelta(seconds=60)


def test_build_exit_price_small_loss():
    ops = load_operating_config()
    assert fill_handler.build_exit_price(0.44, ops.fill_handler) == 0.43


def test_handle_fill_emits_exit():
    ops = load_operating_config()
    market = make_market("Turkey", mid=0.45)
    result = fill_handler.handle_fill(_fill(), market, ops, dry_run=True)
    assert result.exit_intent is not None
    assert result.exit_intent.price == 0.43
    assert not result.kill_switch


def test_kill_switch_in_cancel_window():
    ops = load_operating_config()
    market = make_market("Turkey", mid=0.45, hours_to_kickoff=6.0)
    result = fill_handler.handle_fill(_fill(), market, ops, dry_run=True)
    assert result.kill_switch
    assert result.exit_intent is not None
    assert result.exit_intent.kill_switch
    assert result.exit_intent.size_shares == 500.0
    assert result.pull_quotes


def test_queue_depletion_pulls():
    ops = load_operating_config()
    market = make_market("Turkey", mid=0.45)
    result = fill_handler.handle_fill(_fill(), market, ops, ahead_notional_usd=160.0, dry_run=True)
    assert result.pull_quotes
    assert "queue depletion" in result.reason


def test_volatility_pull():
    ops = load_operating_config()
    assert fill_handler.volatility_pull_triggered(0.50, 0.35, ops.fill_handler)
