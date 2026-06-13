"""Honest paper PnL — horizon exit can lose when price does not recover."""

from world_cup_bot.match_shock import (
    LadderOrder,
    horizon_exit_price,
    simulate_paper_fill,
    simulate_recovery_pnl,
)
from world_cup_bot.shock_tape import ParsedTick


def _tick(ts_ms: int, price: float) -> ParsedTick:
    return ParsedTick(
        ts_ms=ts_ms,
        price=price,
        slug="fifwc-test",
        elapsed_ms=0,
        goal_diff=0,
        bids=(),
    )


def test_horizon_exit_can_be_below_entry():
    ticks = [
        _tick(1000, 0.80),
        _tick(2000, 0.50),  # shock low
        _tick(3000, 0.55),
        _tick(4000, 0.52),  # never recovers to 0.72
    ]
    exit_px = horizon_exit_price(
        ticks,
        2000,
        recovery_target=0.76,
        pre_price=0.80,
        horizon_ms=5000,
    )
    assert exit_px == 0.55  # peak in window, below recovery


def test_paper_fill_loss_when_exit_below_limit():
    plan_orders = (LadderOrder(95, 0.72, 20.0, 0.4),)
    from world_cup_bot.match_shock import LadderPlan

    plan = LadderPlan(
        bucket_key="test",
        pre_price=0.80,
        percentiles_cents={95: 18},
        orders=plan_orders,
        recovery_target_price=0.76,
    )
    fill = simulate_paper_fill(plan, post_shock_low=0.50)
    assert fill is not None
    pnl = simulate_recovery_pnl(fill, exit_price=0.55)
    assert pnl < 0
