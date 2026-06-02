"""REST fill reconciliation — catches WS silent-fill blind spots."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from world_cup_bot import ws_user
from world_cup_bot.clob_auth import ClobAuth
from world_cup_bot.clob_rest import fetch_trades

logger = logging.getLogger(__name__)

_RECONCILE_TRADE_STATUSES = {
    "MATCHED",
    "CONFIRMED",
    "MINED",
    "TRADE_STATUS_MATCHED",
    "TRADE_STATUS_CONFIRMED",
    "TRADE_STATUS_MINED",
}


@dataclass
class ReconcileStats:
    trades_fetched: int = 0
    fills_processed: int = 0
    fills_skipped: int = 0


@dataclass
class ReconcileState:
    """Session cursor for incremental REST passes."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_pass_at: datetime | None = None
    last_after_ts: int | None = None


def rest_trade_to_ws_message(trade: dict[str, Any]) -> dict[str, Any]:
    """Normalize REST /data/trades row → user-channel TRADE shape."""
    status = str(trade.get("status") or "")
    ws_status = "MATCHED" if status in _RECONCILE_TRADE_STATUSES else status
    return {
        "event_type": "trade",
        "type": "TRADE",
        "id": trade.get("id"),
        "market": trade.get("market"),
        "asset_id": trade.get("asset_id"),
        "price": trade.get("price"),
        "size": trade.get("size"),
        "status": ws_status,
        "timestamp": trade.get("match_time") or trade.get("last_update"),
        "matchtime": trade.get("match_time"),
        "last_update": trade.get("last_update"),
        "maker_orders": trade.get("maker_orders") or [],
        "outcome": trade.get("outcome"),
    }


def run_reconcile_pass(
    *,
    clob_url: str,
    auth: ClobAuth,
    poly_address: str,
    maker_address: str,
    ctx: ws_user.FillWatchContext,
    state: ReconcileState,
) -> ReconcileStats:
    """Fetch recent maker trades and process any fills WS missed."""
    stats = ReconcileStats()
    after_ts = state.last_after_ts
    if after_ts is None:
        after_ts = int(state.started_at.timestamp()) - 60

    try:
        trades = fetch_trades(
            clob_url,
            auth,
            poly_address,
            maker_address=maker_address,
            after=after_ts,
        )
    except Exception as exc:
        logger.warning("reconcile fetch failed: %s", exc)
        return stats

    stats.trades_fetched = len(trades)
    now = datetime.now(UTC)
    max_match_ts = after_ts

    for trade in trades:
        match_time = trade.get("match_time")
        if match_time is not None:
            try:
                max_match_ts = max(max_match_ts, int(str(match_time)))
            except ValueError:
                pass

        status = str(trade.get("status") or "")
        if status not in _RECONCILE_TRADE_STATUSES:
            stats.fills_skipped += 1
            continue

        msg = rest_trade_to_ws_message(trade)
        if not ws_user.is_matched_trade_message(msg):
            stats.fills_skipped += 1
            continue

        before = ctx.stats.fills_processed
        ws_user.process_trade_message(msg, ctx)
        delta = ctx.stats.fills_processed - before
        if delta:
            stats.fills_processed += delta
            logger.info(
                "reconcile recovered %d fill(s) trade_id=%s",
                delta,
                trade.get("id"),
            )
        else:
            stats.fills_skipped += 1

    state.last_pass_at = now
    state.last_after_ts = max_match_ts
    return stats
