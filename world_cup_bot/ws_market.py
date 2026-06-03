"""Polymarket CLOB market-channel WebSocket — public orderbook / price feed (Module 8)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from world_cup_bot.match_shock import BookLevel

logger = logging.getLogger(__name__)

DEFAULT_WS_MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PING_INTERVAL_SEC = 10


@dataclass
class MarketWatchStats:
    messages: int = 0
    book_events: int = 0
    price_changes: int = 0
    ticks_written: int = 0


def build_market_subscription(asset_ids: list[str]) -> dict[str, Any]:
    return {"assets_ids": asset_ids, "type": "market"}


def parse_market_ws_text(raw: str) -> dict[str, Any] | list[Any] | None:
    if raw == "PONG":
        return None
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("non-json market ws payload: %r", raw[:120])
        return None
    return msg


def _parse_levels(raw: list[Any] | None) -> tuple[BookLevel, ...]:
    out: list[BookLevel] = []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        try:
            out.append(BookLevel(price=float(row["price"]), size=float(row.get("size", 0))))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(out)


def _ts_ms_from_msg(msg: dict[str, Any]) -> int:
    for key in ("timestamp", "ts", "matchtime"):
        raw = msg.get(key)
        if raw is None or raw == "":
            continue
        ts = int(str(raw))
        if ts < 10_000_000_000:
            ts *= 1000
        return ts
    import time

    return int(time.time() * 1000)


def extract_market_ticks(
    msg: dict[str, Any] | list[Any],
    *,
    asset_to_slug: dict[str, str],
) -> list[dict[str, Any]]:
    """Map market-channel messages → shock tape tick dicts."""
    if isinstance(msg, list):
        ticks: list[dict[str, Any]] = []
        for item in msg:
            if isinstance(item, dict):
                ticks.extend(extract_market_ticks(item, asset_to_slug=asset_to_slug))
        return ticks

    event_type = str(msg.get("event_type") or msg.get("type") or "").lower()
    asset_id = str(msg.get("asset_id") or msg.get("assetId") or "")

    if event_type == "price_change":
        ticks: list[dict[str, Any]] = []
        for change in msg.get("price_changes") or []:
            if not isinstance(change, dict):
                continue
            aid = str(change.get("asset_id") or asset_id)
            s = asset_to_slug.get(aid)
            if not s:
                continue
            price_raw = change.get("price")
            if price_raw is None:
                continue
            ticks.append(
                {
                    "ts_ms": _ts_ms_from_msg(msg),
                    "price": float(price_raw),
                    "slug": s,
                    "elapsed_ms": 0,
                    "goal_diff": 0,
                }
            )
        return ticks

    slug = asset_to_slug.get(asset_id)
    if not slug:
        return []

    ts_ms = _ts_ms_from_msg(msg)
    ticks: list[dict[str, Any]] = []

    if event_type == "book" or ("bids" in msg and "asks" in msg):
        bids = _parse_levels(msg.get("bids"))
        asks = _parse_levels(msg.get("asks"))
        mid = None
        if bids and asks:
            mid = (bids[0].price + asks[0].price) / 2.0
        elif msg.get("price") is not None:
            mid = float(msg["price"])
        tick: dict[str, Any] = {
            "ts_ms": ts_ms,
            "slug": slug,
            "elapsed_ms": 0,
            "goal_diff": 0,
        }
        if mid is not None:
            tick["price"] = mid
        if bids:
            tick["bids"] = [{"price": b.price, "size": b.size} for b in bids[:5]]
        if asks:
            tick["asks"] = [{"price": a.price, "size": a.size} for a in asks[:5]]
        ticks.append(tick)
        return ticks

    if msg.get("price") is not None:
        ticks.append(
            {
                "ts_ms": ts_ms,
                "price": float(msg["price"]),
                "slug": slug,
                "elapsed_ms": 0,
                "goal_diff": 0,
            }
        )
    return ticks


@dataclass
class MarketTapeContext:
    asset_to_slug: dict[str, str]
    on_ticks: Callable[[list[dict[str, Any]]], None]
    stats: MarketWatchStats = field(default_factory=MarketWatchStats)


async def _ping_loop(ws: Any, *, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=PING_INTERVAL_SEC)
        except TimeoutError:
            await ws.send("PING")


async def watch_market_tape(
    *,
    ws_url: str,
    asset_ids: list[str],
    ctx: MarketTapeContext,
) -> None:
    """Subscribe to market channel and invoke on_ticks for each parsed shock tick."""
    try:
        import websockets
    except ImportError as exc:
        raise ImportError("pip install 'world-cup-bot[live]' for WebSocket support") from exc

    sub = build_market_subscription(asset_ids)
    stop = asyncio.Event()
    logger.info("connecting %s — %d asset ids", ws_url, len(asset_ids))

    async with websockets.connect(ws_url, ping_interval=None) as ws:
        await ws.send(json.dumps(sub))
        ping_task = asyncio.create_task(_ping_loop(ws, stop=stop))
        try:
            async for raw in ws:
                ctx.stats.messages += 1
                msg = parse_market_ws_text(raw if isinstance(raw, str) else raw.decode())
                if msg is None:
                    continue
                if isinstance(msg, dict):
                    et = str(msg.get("event_type") or "").lower()
                    if et == "book":
                        ctx.stats.book_events += 1
                    elif et == "price_change":
                        ctx.stats.price_changes += 1
                ticks = extract_market_ticks(msg, asset_to_slug=ctx.asset_to_slug)
                if ticks:
                    ctx.on_ticks(ticks)
                    ctx.stats.ticks_written += len(ticks)
        finally:
            stop.set()
            ping_task.cancel()
            await asyncio.gather(ping_task, return_exceptions=True)
