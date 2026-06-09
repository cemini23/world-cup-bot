"""Kalshi order placement for cross-venue Phase C (limit orders)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from world_cup_bot.http_client import (
    GET_HOST_ALLOWLIST,
    USER_AGENT,
    _hostname,
    _reject_private_host,
)
from world_cup_bot.kalshi_auth import SIGN_PATH_PREFIX, KalshiAuth, authenticated_headers


class KalshiOrderError(RuntimeError):
    """Kalshi rejected or failed an order request."""


def _validate_kalshi_api_url(url: str) -> None:
    host = _hostname(url)
    _reject_private_host(host)
    if host not in GET_HOST_ALLOWLIST:
        raise KalshiOrderError(f"Kalshi API host not allowlisted: {host}")


@dataclass(frozen=True)
class KalshiOrderRequest:
    ticker: str
    action: str  # buy | sell
    side: str  # yes | no
    count: int
    yes_price_cents: int | None = None
    no_price_cents: int | None = None
    client_order_id: str | None = None


@dataclass(frozen=True)
class KalshiOrderResult:
    order_id: str
    ticker: str
    status: str
    dry_run: bool
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "ticker": self.ticker,
            "status": self.status,
            "dry_run": self.dry_run,
            "raw": self.raw,
        }


def _order_path() -> str:
    return f"{SIGN_PATH_PREFIX}/portfolio/orders"


def _price_cents(probability: float) -> int:
    return max(1, min(99, int(round(probability * 100))))


def build_kalshi_order(
    *,
    ticker: str,
    leg: str,
    price: float,
    notional_usd: float,
) -> KalshiOrderRequest:
    """Map arb leg BUY/SELL on YES equivalent to Kalshi order."""
    leg = leg.upper()
    count = max(1, int(notional_usd / max(price, 0.01)))
    if leg == "BUY":
        return KalshiOrderRequest(
            ticker=ticker,
            action="buy",
            side="yes",
            count=count,
            yes_price_cents=_price_cents(price),
        )
    return KalshiOrderRequest(
        ticker=ticker,
        action="sell",
        side="yes",
        count=count,
        yes_price_cents=_price_cents(price),
    )


def _body_from_request(req: KalshiOrderRequest) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ticker": req.ticker,
        "action": req.action,
        "side": req.side,
        "type": "limit",
        "count": req.count,
    }
    if req.yes_price_cents is not None:
        body["yes_price"] = req.yes_price_cents
    if req.no_price_cents is not None:
        body["no_price"] = req.no_price_cents
    if req.client_order_id:
        body["client_order_id"] = req.client_order_id
    return body


def create_limit_order(
    auth: KalshiAuth,
    req: KalshiOrderRequest,
    *,
    base_url: str,
    dry_run: bool = False,
    opener: Any | None = None,
) -> KalshiOrderResult:
    path = _order_path()
    body = _body_from_request(req)
    if dry_run:
        return KalshiOrderResult(
            order_id=f"dry-kalshi-{req.ticker}",
            ticker=req.ticker,
            status="dry_run",
            dry_run=True,
            raw={"request": body},
        )

    url = f"{base_url.rstrip('/')}/portfolio/orders"
    _validate_kalshi_api_url(url)
    data = json.dumps(body).encode()
    headers = authenticated_headers(auth, method="POST", path=path)
    headers["User-Agent"] = USER_AGENT
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        if opener is not None:
            with opener(request, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
        else:
            with urllib.request.urlopen(request, timeout=30) as resp:
                payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() if exc.fp else str(exc)
        raise KalshiOrderError(f"Kalshi POST /portfolio/orders {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise KalshiOrderError(f"Kalshi order request failed: {exc}") from exc

    order = payload.get("order") or payload
    order_id = str(order.get("order_id") or order.get("id") or "")
    if not order_id:
        raise KalshiOrderError(f"Kalshi order response missing id: {payload}")
    return KalshiOrderResult(
        order_id=order_id,
        ticker=req.ticker,
        status=str(order.get("status") or "submitted"),
        dry_run=False,
        raw=payload,
    )


def cancel_order(
    auth: KalshiAuth,
    order_id: str,
    *,
    base_url: str,
    dry_run: bool = False,
    opener: Any | None = None,
) -> dict[str, Any]:
    path = f"{SIGN_PATH_PREFIX}/portfolio/orders/{order_id}"
    if dry_run:
        return {"order_id": order_id, "status": "cancel_dry_run"}

    url = f"{base_url.rstrip('/')}/portfolio/orders/{order_id}"
    _validate_kalshi_api_url(url)
    headers = authenticated_headers(auth, method="DELETE", path=path)
    headers["User-Agent"] = USER_AGENT
    request = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        if opener is not None:
            with opener(request, timeout=30) as resp:
                return json.loads(resp.read().decode())
        with urllib.request.urlopen(request, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode() if exc.fp else str(exc)
        raise KalshiOrderError(f"Kalshi DELETE order {exc.code}: {detail}") from exc
