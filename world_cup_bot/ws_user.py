"""Polymarket CLOB user-channel WebSocket — venue-confirmed fill ingestion (Module 4)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from world_cup_bot.clob_auth import ClobAuth
from world_cup_bot.config import Settings
from world_cup_bot.fill_handler import (
    FillEvent,
    FillHandlerResult,
    handle_fill,
    submit_exit,
    volatility_pull_triggered,
)
from world_cup_bot.ledger import record_exit_intent, record_fill
from world_cup_bot.liquidity_scanner import fetch_ahead_bid_notional_usd
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.operating_config import OperatingConfig
from world_cup_bot.reconcile import ReconcileState, run_reconcile_pass
from world_cup_bot.scanner import AdvanceMarket, discover_advance_markets

logger = logging.getLogger(__name__)

DEFAULT_WS_USER_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
PING_INTERVAL_SEC = 10
RECONCILE_INTERVAL_SEC = 30


@dataclass
class WatchStats:
    messages: int = 0
    trades_seen: int = 0
    fills_processed: int = 0
    fills_skipped_dedup: int = 0
    fills_skipped_unknown_market: int = 0


@dataclass
class FillWatchContext:
    """Runtime state for one watch session."""

    markets_by_condition: dict[str, AdvanceMarket]
    markets: list[AdvanceMarket]
    operating: OperatingConfig
    version_spec: StrategyVersionSpec
    ledger_path: str
    dry_run: bool
    record: bool
    settings: Settings | None = None
    clob_url: str = "https://clob.polymarket.com"
    auth: ClobAuth | None = None
    poly_address: str = ""
    maker_address: str = ""
    reconcile_state: ReconcileState = field(default_factory=ReconcileState)
    seen_fill_keys: set[str] = field(default_factory=set)
    peak_mid_by_team: dict[str, float] = field(default_factory=dict)
    vol_cooldown_until: dict[str, datetime] = field(default_factory=dict)
    stats: WatchStats = field(default_factory=WatchStats)
    halt: Any = field(default_factory=lambda: _trading_halt())
    on_result: Callable[[FillHandlerResult], None] | None = None


def _trading_halt():
    from world_cup_bot.order_manager import TradingHalt

    return TradingHalt()


def build_user_subscription(auth: ClobAuth, condition_ids: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "auth": auth.subscription_fields(),
        "type": "user",
    }
    if condition_ids:
        payload["markets"] = condition_ids
    return payload


def parse_ws_text(raw: str) -> dict[str, Any] | None:
    if raw == "PONG":
        return None
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("non-json ws payload: %r", raw[:120])
        return None
    if not isinstance(msg, dict):
        return None
    return msg


def _parse_timestamp(msg: dict[str, Any]) -> datetime:
    for key in ("timestamp", "matchtime", "last_update"):
        raw = msg.get(key)
        if raw is None or raw == "":
            continue
        ts = int(str(raw))
        if ts > 1_000_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=UTC)
    return datetime.now(UTC)


def _side_from_outcome(
    outcome: str | None,
    asset_id: str | None,
    market: AdvanceMarket,
) -> str | None:
    if outcome:
        upper = outcome.upper()
        if upper in {"YES", "NO"}:
            return upper
    if asset_id == market.yes_token_id:
        return "YES"
    if asset_id == market.no_token_id:
        return "NO"
    return None


def is_matched_trade_message(msg: dict[str, Any]) -> bool:
    if msg.get("event_type") != "trade" and msg.get("type") != "TRADE":
        return False
    return msg.get("status") == "MATCHED"


def extract_maker_fills(
    msg: dict[str, Any],
    markets_by_condition: dict[str, AdvanceMarket],
) -> list[FillEvent]:
    """Map user-channel TRADE (MATCHED) → FillEvent for our maker legs only."""
    if not is_matched_trade_message(msg):
        return []

    condition_id = str(msg.get("market") or "")
    market = markets_by_condition.get(condition_id)
    if market is None:
        return []

    filled_at = _parse_timestamp(msg)
    trade_id = str(msg.get("id") or "")
    fills: list[FillEvent] = []

    for maker in msg.get("maker_orders") or []:
        if not isinstance(maker, dict):
            continue
        order_id = str(maker.get("order_id") or "")
        if not order_id:
            continue
        asset_id = str(maker.get("asset_id") or msg.get("asset_id") or "")
        side = _side_from_outcome(maker.get("outcome"), asset_id or None, market)
        if side is None:
            continue
        try:
            price = float(maker.get("price") or msg.get("price") or 0)
            shares = float(maker.get("matched_amount") or maker.get("size") or msg.get("size") or 0)
        except (TypeError, ValueError):
            continue
        if shares <= 0 or price <= 0:
            continue
        token_id = market.yes_token_id if side == "YES" else market.no_token_id
        fills.append(
            FillEvent(
                order_id=order_id,
                team=market.team,
                side=side,  # type: ignore[arg-type]
                token_id=token_id,
                fill_price=price,
                fill_shares=shares,
                filled_at=filled_at,
                maker_order_id=order_id,
            )
        )

    if not fills and trade_id:
        logger.debug("trade %s had no parseable maker_orders", trade_id)
    return fills


def fill_dedup_key(trade_id: str, fill: FillEvent) -> str:
    return f"{trade_id}:{fill.order_id}"


def process_trade_message(msg: dict[str, Any], ctx: FillWatchContext) -> list[FillHandlerResult]:
    """Parse TRADE → handle_fill → optional ledger; returns results for this message."""
    if not is_matched_trade_message(msg):
        return []

    ctx.stats.trades_seen += 1
    trade_id = str(msg.get("id") or "")
    condition_id = str(msg.get("market") or "")
    if condition_id and condition_id not in ctx.markets_by_condition:
        ctx.stats.fills_skipped_unknown_market += 1
        return []

    results: list[FillHandlerResult] = []
    for fill in extract_maker_fills(msg, ctx.markets_by_condition):
        key = fill_dedup_key(trade_id, fill)
        if key in ctx.seen_fill_keys:
            ctx.stats.fills_skipped_dedup += 1
            continue
        ctx.seen_fill_keys.add(key)

        market = ctx.markets_by_condition[condition_id]
        ahead_usd = 0.0
        try:
            ahead_usd = fetch_ahead_bid_notional_usd(
                ctx.clob_url,
                fill.token_id,
                fill.fill_price,
            )
        except Exception as exc:  # noqa: BLE001 — fail open on book fetch
            logger.warning("ahead depth fetch failed for %s: %s", fill.team, exc)

        result = handle_fill(
            fill,
            market,
            ctx.operating,
            ahead_notional_usd=ahead_usd,
            dry_run=ctx.dry_run,
        )
        ctx.stats.fills_processed += 1

        if ctx.record:
            if not record_fill(
                path=ctx.ledger_path,
                spec=ctx.version_spec,
                team=fill.team,
                side=fill.side,
                order_id=fill.order_id,
                price=fill.fill_price,
                size_shares=fill.fill_shares,
            ):
                ctx.stats.fills_skipped_dedup += 1
                logger.info("ledger dedup skip order_id=%s", fill.order_id)
                continue
            if result.exit_intent:
                record_exit_intent(
                    result.exit_intent,
                    ctx.version_spec,
                    path=ctx.ledger_path,
                    fill_order_id=fill.order_id,
                    dry_run=ctx.dry_run,
                )

        if result.exit_intent:
            try:
                submit_exit(result.exit_intent, dry_run=ctx.dry_run, settings=ctx.settings)
            except Exception as exc:
                logger.error(
                    "exit POST failed for %s %s (fill continues): %s",
                    fill.team,
                    fill.side,
                    exc,
                )

        if ctx.settings is not None and (result.kill_switch or result.pull_quotes):
            from world_cup_bot.order_manager import apply_fill_safety_actions

            apply_fill_safety_actions(
                ctx.settings,
                ctx.markets,
                team=fill.team,
                kill_switch=result.kill_switch,
                pull_quotes=result.pull_quotes,
                halt=ctx.halt,
                dry_run=ctx.dry_run,
                ledger_path=ctx.ledger_path,
                version_spec=ctx.version_spec,
            )

        if ctx.on_result:
            ctx.on_result(result)
        results.append(result)
        logger.info(
            "fill %s %s %s @ %.4f x %.1f kill=%s pull=%s",
            fill.order_id,
            fill.team,
            fill.side,
            fill.fill_price,
            fill.fill_shares,
            result.kill_switch,
            result.pull_quotes,
        )
    return results


def market_safety_pass(ctx: FillWatchContext) -> None:
    """Refresh Gamma mids, enforce vol pull + calendar cancel during watch."""
    if ctx.settings is None:
        return

    from world_cup_bot.order_manager import apply_fill_safety_actions, cancel_for_cancel_window

    fresh = discover_advance_markets(
        ctx.settings.gamma_url,
        min_hours_before_kickoff=ctx.settings.min_hours_before_kickoff,
    )
    ctx.markets = fresh
    ctx.markets_by_condition = {m.condition_id: m for m in fresh if m.condition_id}

    now = datetime.now(UTC)
    cooldown_min = ctx.operating.fill_handler.vol_cooldown_minutes

    for market in fresh:
        if market.mid is None:
            continue
        team = market.team
        peak = ctx.peak_mid_by_team.get(team, market.mid)
        if market.mid > peak:
            ctx.peak_mid_by_team[team] = market.mid
            peak = market.mid

        cooldown_until = ctx.vol_cooldown_until.get(team)
        if cooldown_until is not None and now < cooldown_until:
            continue

        if volatility_pull_triggered(peak, market.mid, ctx.operating.fill_handler):
            logger.warning(
                "volatility pull %s mid %.3f peak %.3f",
                team,
                market.mid,
                peak,
            )
            apply_fill_safety_actions(
                ctx.settings,
                ctx.markets,
                team=team,
                kill_switch=False,
                pull_quotes=True,
                halt=ctx.halt,
                dry_run=ctx.dry_run,
                ledger_path=ctx.ledger_path,
                version_spec=ctx.version_spec,
            )
            ctx.peak_mid_by_team[team] = market.mid
            ctx.vol_cooldown_until[team] = now + timedelta(minutes=cooldown_min)

    cancel_for_cancel_window(
        ctx.settings,
        ctx.markets,
        dry_run=ctx.dry_run,
        ledger_path=ctx.ledger_path,
        version_spec=ctx.version_spec,
    )


async def reconciliation_loop(*, stop: asyncio.Event, ctx: FillWatchContext) -> None:
    """Periodic REST /data/trades pass — WS alone can miss silent fills."""
    if ctx.auth is None or not ctx.poly_address or not ctx.maker_address:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=RECONCILE_INTERVAL_SEC)
            except TimeoutError:
                logger.debug("reconcile skipped — L2 creds or address not configured")
        return

    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=RECONCILE_INTERVAL_SEC)
        except TimeoutError:
            stats = run_reconcile_pass(
                clob_url=ctx.clob_url,
                auth=ctx.auth,
                poly_address=ctx.poly_address,
                maker_address=ctx.maker_address,
                ctx=ctx,
                state=ctx.reconcile_state,
            )
            if stats.fills_processed:
                logger.info(
                    "reconcile pass: fetched=%d recovered=%d",
                    stats.trades_fetched,
                    stats.fills_processed,
                )
            else:
                logger.debug(
                    "reconcile pass: fetched=%d skipped=%d",
                    stats.trades_fetched,
                    stats.fills_skipped,
                )
            market_safety_pass(ctx)


async def _ping_loop(ws: Any, *, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=PING_INTERVAL_SEC)
        except TimeoutError:
            await ws.send("PING")


async def watch_fills(
    *,
    ws_url: str,
    auth: ClobAuth,
    markets: list[AdvanceMarket],
    ctx: FillWatchContext,
) -> None:
    """Connect to user channel, subscribe to condition IDs, process fills until cancelled."""
    try:
        import websockets
    except ImportError as exc:
        raise ImportError("pip install 'world-cup-bot[live]' for WebSocket support") from exc

    condition_ids = sorted({m.condition_id for m in markets if m.condition_id})
    sub = build_user_subscription(auth, condition_ids)
    stop = asyncio.Event()

    logger.info(
        "connecting %s — %d condition ids (%d teams)",
        ws_url,
        len(condition_ids),
        len(markets),
    )

    async with websockets.connect(ws_url, ping_interval=None) as ws:
        await ws.send(json.dumps(sub))
        ping_task = asyncio.create_task(_ping_loop(ws, stop=stop))
        reconcile_task = asyncio.create_task(reconciliation_loop(stop=stop, ctx=ctx))
        try:
            async for raw in ws:
                ctx.stats.messages += 1
                msg = parse_ws_text(raw if isinstance(raw, str) else raw.decode())
                if msg is None:
                    continue
                process_trade_message(msg, ctx)
        finally:
            stop.set()
            ping_task.cancel()
            reconcile_task.cancel()
            await asyncio.gather(ping_task, reconcile_task, return_exceptions=True)
