"""Polymarket Data API — public trade history for match-shock backtest tapes."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
from collections.abc import Iterator
from typing import Any

from world_cup_bot.http_client import urlopen_get

DEFAULT_DATA_API = "https://data-api.polymarket.com"
DEFAULT_PAGE_SIZE = 100
DEFAULT_SLEEP_S = 0.05


def fetch_trades_page(
    *,
    condition_id: str | None = None,
    user: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    offset: int = 0,
    taker_only: bool = False,
    data_api: str = DEFAULT_DATA_API,
) -> list[dict[str, Any]]:
    params: dict[str, str | int] = {
        "limit": limit,
        "offset": offset,
        "takerOnly": "true" if taker_only else "false",
    }
    if condition_id:
        params["market"] = condition_id
    if user:
        params["user"] = user
    qs = urllib.parse.urlencode(params)
    url = f"{data_api.rstrip('/')}/trades?{qs}"
    try:
        with urlopen_get(url, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def iter_market_trades(
    condition_id: str,
    *,
    max_trades: int | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    sleep_s: float = DEFAULT_SLEEP_S,
    data_api: str = DEFAULT_DATA_API,
) -> Iterator[dict[str, Any]]:
    offset = 0
    fetched = 0
    while True:
        page = fetch_trades_page(
            condition_id=condition_id,
            limit=page_size,
            offset=offset,
            data_api=data_api,
        )
        if not page:
            break
        for row in page:
            yield row
            fetched += 1
            if max_trades is not None and fetched >= max_trades:
                return
        if len(page) < page_size:
            break
        offset += page_size
        if sleep_s:
            time.sleep(sleep_s)


def trade_to_shock_tick(row: dict[str, Any], *, slug: str) -> dict[str, Any]:
    """Normalize Data API trade row → backtest JSONL tick."""
    ts_raw = row.get("timestamp")
    if ts_raw is not None and int(ts_raw) < 10_000_000_000:
        ts_ms = int(ts_raw) * 1000
    else:
        ts_ms = int(ts_raw or 0)
    price = float(row.get("price") or 0)
    return {
        "ts_ms": ts_ms,
        "price": price,
        "slug": slug,
        "elapsed_ms": 0,
        "goal_diff": 0,
    }
