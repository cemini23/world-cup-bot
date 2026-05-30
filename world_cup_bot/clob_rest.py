"""Authenticated CLOB REST reads (stdlib + L2 HMAC)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from world_cup_bot.clob_auth import ClobAuth
from world_cup_bot.clob_signing import create_level_2_headers
from world_cup_bot.http_client import USER_AGENT, urlopen_get

END_CURSOR = "LTE="
PATH_ORDERS = "/data/orders"
PATH_TRADES = "/data/trades"
PATH_REWARDS_USER = "/rewards/user"


@dataclass(frozen=True)
class GeoblockStatus:
    blocked: bool
    ip: str
    country: str
    region: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> GeoblockStatus:
        return cls(
            blocked=bool(payload.get("blocked")),
            ip=str(payload.get("ip") or ""),
            country=str(payload.get("country") or ""),
            region=str(payload.get("region") or ""),
        )


def fetch_geoblock() -> GeoblockStatus:
    with urlopen_get("https://polymarket.com/api/geoblock", timeout=15) as resp:
        return GeoblockStatus.from_payload(json.loads(resp.read().decode()))


def fetch_clob_time(clob_url: str) -> int:
    with urlopen_get(f"{clob_url.rstrip('/')}/time", timeout=15) as resp:
        payload = json.loads(resp.read().decode())
    if isinstance(payload, dict):
        return int(payload.get("timestamp") or payload.get("time") or 0)
    return int(payload)


def fetch_book(clob_url: str, token_id: str, *, timeout: float = 15) -> dict[str, Any]:
    """Public GET /book — no auth (requires User-Agent via http_client)."""
    qs = urllib.parse.urlencode({"token_id": token_id})
    url = f"{clob_url.rstrip('/')}/book?{qs}"
    with urlopen_get(url, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    if not isinstance(payload, dict):
        raise ValueError(f"unexpected /book payload type: {type(payload)}")
    return payload


def _authenticated_get(
    clob_url: str,
    path: str,
    auth: ClobAuth,
    address: str,
    query: dict[str, str] | None = None,
    *,
    timeout: float = 30,
) -> dict[str, Any]:
    qs = urllib.parse.urlencode(query or {})
    url_path = path if not qs else f"{path}?{qs}"
    headers = create_level_2_headers(
        auth,
        address=address,
        method="GET",
        request_path=path,
    )
    headers["Accept"] = "application/json"
    headers["User-Agent"] = USER_AGENT
    req = urllib.request.Request(f"{clob_url.rstrip('/')}{url_path}", headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_open_orders(
    clob_url: str,
    auth: ClobAuth,
    address: str,
    *,
    market: str | None = None,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """Paginated GET /data/orders."""
    results: list[dict[str, Any]] = []
    cursor = "MA=="
    pages = 0
    while cursor != END_CURSOR and pages < max_pages:
        query: dict[str, str] = {"next_cursor": cursor}
        if market:
            query["market"] = market
        payload = _authenticated_get(clob_url, PATH_ORDERS, auth, address, query)
        results.extend(payload.get("data") or [])
        cursor = str(payload.get("next_cursor") or END_CURSOR)
        pages += 1
    return results


def fetch_trades(
    clob_url: str,
    auth: ClobAuth,
    address: str,
    *,
    maker_address: str,
    market: str | None = None,
    after: int | None = None,
    max_pages: int = 3,
) -> list[dict[str, Any]]:
    """Paginated GET /data/trades for maker reconciliation."""
    results: list[dict[str, Any]] = []
    cursor = "MA=="
    pages = 0
    while cursor != END_CURSOR and pages < max_pages:
        query: dict[str, str] = {
            "maker_address": maker_address,
            "next_cursor": cursor,
        }
        if market:
            query["market"] = market
        if after is not None:
            query["after"] = str(after)
        payload = _authenticated_get(clob_url, PATH_TRADES, auth, address, query)
        results.extend(payload.get("data") or [])
        cursor = str(payload.get("next_cursor") or END_CURSOR)
        pages += 1
    return results


def fetch_user_rewards_for_date(
    clob_url: str,
    auth: ClobAuth,
    address: str,
    *,
    date: str,
    maker_address: str | None = None,
    signature_type: int | None = None,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """Paginated GET /rewards/user — earnings per market for YYYY-MM-DD."""
    results: list[dict[str, Any]] = []
    cursor = "MA=="
    pages = 0
    while cursor != END_CURSOR and pages < max_pages:
        query: dict[str, str] = {"date": date, "next_cursor": cursor}
        if maker_address:
            query["maker_address"] = maker_address
        if signature_type is not None:
            query["signature_type"] = str(signature_type)
        payload = _authenticated_get(clob_url, PATH_REWARDS_USER, auth, address, query)
        results.extend(payload.get("data") or [])
        cursor = str(payload.get("next_cursor") or END_CURSOR)
        pages += 1
    return results
