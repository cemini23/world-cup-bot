"""Fill handler — limit exit within 60s, queue depletion, kill switch (Module 4)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from world_cup_bot.operating_config import FillHandlerOps, OperatingConfig
from world_cup_bot.quoter import _tick_price
from world_cup_bot.scanner import AdvanceMarket

Side = Literal["YES", "NO"]


@dataclass(frozen=True)
class FillEvent:
    """Venue-confirmed fill (never inferred from timeout — blind-spot #3)."""

    order_id: str
    team: str
    side: Side
    token_id: str
    fill_price: float
    fill_shares: float
    filled_at: datetime
    maker_order_id: str | None = None


@dataclass(frozen=True)
class ExitIntent:
    """Resting limit exit — never market cross unless emergency flatten on prod."""

    team: str
    side: Side
    token_id: str
    order_id: str
    price: float
    size_shares: float
    due_by: datetime
    reason: str
    kill_switch: bool = False


@dataclass(frozen=True)
class FillHandlerResult:
    fill: FillEvent
    exit_intent: ExitIntent | None
    pull_quotes: bool
    kill_switch: bool
    reason: str


def _new_exit_order_id(team: str, side: Side, *, dry_run: bool) -> str:
    prefix = "exit-dry" if dry_run else "exit-live"
    slug = team.lower().replace(" ", "-")[:20]
    return f"{prefix}-{slug}-{side.lower()}-{secrets.token_hex(4)}"


def exit_due_by(filled_at: datetime, ops: FillHandlerOps) -> datetime:
    return filled_at + timedelta(seconds=ops.exit_within_seconds)


def build_exit_price(fill_price: float, ops: FillHandlerOps) -> float:
    """Break-even or small loss (limit only)."""
    tick = 0.01
    loss = ops.exit_loss_ticks * tick
    return _tick_price(max(tick, fill_price - loss))


def should_kill_switch(market: AdvanceMarket, filled_at: datetime | None = None) -> bool:
    """Live-window or cancel-window fill → flatten + halt."""
    _ = filled_at
    if market.must_cancel:
        return True
    if market.hours_to_kickoff is not None and (
        market.hours_to_kickoff < market.min_hours_before_kickoff
    ):
        return True
    return False


def queue_depletion_triggered(ahead_notional_usd: float, ops: FillHandlerOps) -> bool:
    return ahead_notional_usd >= ops.queue_depletion_usd


def volatility_pull_triggered(
    local_peak_mid: float,
    current_mid: float,
    ops: FillHandlerOps,
) -> bool:
    if local_peak_mid <= 0:
        return False
    drop = (local_peak_mid - current_mid) / local_peak_mid
    return drop >= ops.vol_drop_pct


def handle_fill(
    fill: FillEvent,
    market: AdvanceMarket,
    operating: OperatingConfig,
    *,
    ahead_notional_usd: float = 0.0,
    dry_run: bool = True,
) -> FillHandlerResult:
    """Process a venue-confirmed fill → exit intent + pull/kill flags."""
    ops = operating.fill_handler
    kill = should_kill_switch(market, fill.filled_at)
    pull = queue_depletion_triggered(ahead_notional_usd, ops)

    if kill:
        return FillHandlerResult(
            fill=fill,
            exit_intent=None,
            pull_quotes=True,
            kill_switch=True,
            reason="kill_switch — fill inside cancel/live window",
        )

    exit_price = build_exit_price(fill.fill_price, ops)
    due = exit_due_by(fill.filled_at, ops)
    reason = "limit exit ≤60s at break-even/small loss"
    if pull:
        reason = f"queue depletion ≥${ops.queue_depletion_usd:.0f} — exit + pull quotes"

    exit_intent = ExitIntent(
        team=fill.team,
        side=fill.side,
        token_id=fill.token_id,
        order_id=_new_exit_order_id(fill.team, fill.side, dry_run=dry_run),
        price=exit_price,
        size_shares=fill.fill_shares,
        due_by=due,
        reason=reason,
        kill_switch=False,
    )

    return FillHandlerResult(
        fill=fill,
        exit_intent=exit_intent,
        pull_quotes=pull,
        kill_switch=False,
        reason=reason,
    )


def submit_exit(intent: ExitIntent, *, dry_run: bool = True) -> ExitIntent:
    if dry_run:
        return intent
    raise NotImplementedError(
        "Live CLOB exit POST not enabled in public OSS — set DRY_RUN=true or use Cemini module"
    )
