"""Live CLOB order POST via py-clob-client (optional [live] extra)."""

from __future__ import annotations

import os
from typing import Any

from world_cup_bot.config import Settings
from world_cup_bot.fill_handler import ExitIntent
from world_cup_bot.quoter import QuoteIntent


class LiveClobNotConfiguredError(RuntimeError):
    """Raised when DRY_RUN=false but live trading deps or keys are missing."""


class LiveClobPostError(RuntimeError):
    """Raised when CLOB rejects an order POST."""


def _require_private_key() -> str:
    key = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if not key:
        raise LiveClobNotConfiguredError(
            "POLYMARKET_PRIVATE_KEY required for live POST (DRY_RUN=false)"
        )
    return key


def _signature_type() -> int:
    raw = os.environ.get("POLYMARKET_SIGNATURE_TYPE", "2").strip()
    return int(raw)


def _funder_address() -> str | None:
    raw = os.environ.get("POLYMARKET_FUNDER_ADDRESS", "").strip()
    return raw or None


def build_clob_client(settings: Settings) -> Any:
    """Return configured py-clob-client ClobClient."""
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
    except ImportError as exc:
        raise LiveClobNotConfiguredError(
            "pip install -e '.[live]' for live CLOB POST (py-clob-client)"
        ) from exc

    from world_cup_bot.clob_auth import load_clob_auth

    auth = load_clob_auth()
    creds = ApiCreds(
        api_key=auth.api_key,
        api_secret=auth.secret,
        api_passphrase=auth.passphrase,
    )
    funder = _funder_address()
    kwargs: dict[str, Any] = {
        "host": settings.clob_url,
        "key": _require_private_key(),
        "chain_id": 137,
        "creds": creds,
        "signature_type": _signature_type(),
    }
    if funder:
        kwargs["funder"] = funder
    return ClobClient(**kwargs)


def post_quote_intent(client: Any, intent: QuoteIntent) -> dict[str, Any]:
    """Post resting limit bid (post-only GTC)."""
    from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions
    from py_clob_client.order_builder.constants import BUY

    order_args = OrderArgs(
        token_id=intent.token_id,
        price=intent.price,
        size=intent.size_shares,
        side=BUY,
    )
    options = PartialCreateOrderOptions(tick_size="0.01", neg_risk=False)
    order = client.create_order(order_args, options)
    resp = client.post_order(order, post_only=True)
    if not isinstance(resp, dict):
        return {"response": resp}
    if resp.get("error") or resp.get("success") is False:
        raise LiveClobPostError(str(resp.get("error") or resp))
    return resp


def post_exit_intent(client: Any, intent: ExitIntent) -> dict[str, Any]:
    """Post resting limit sell to exit a fill (GTC, not post-only)."""
    from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions
    from py_clob_client.order_builder.constants import SELL

    order_args = OrderArgs(
        token_id=intent.token_id,
        price=intent.price,
        size=intent.size_shares,
        side=SELL,
    )
    options = PartialCreateOrderOptions(tick_size="0.01", neg_risk=False)
    order = client.create_order(order_args, options)
    resp = client.post_order(order)
    if not isinstance(resp, dict):
        return {"response": resp}
    if resp.get("error") or resp.get("success") is False:
        raise LiveClobPostError(str(resp.get("error") or resp))
    return resp


def cancel_order_id(client: Any, order_id: str) -> dict[str, Any]:
    """Cancel one resting order by id."""
    resp = client.cancel(order_id)
    if isinstance(resp, dict) and (resp.get("error") or resp.get("success") is False):
        raise LiveClobPostError(str(resp.get("error") or resp))
    return resp if isinstance(resp, dict) else {"response": resp}


def cancel_order_ids(client: Any, order_ids: list[str]) -> list[dict[str, Any]]:
    """Cancel multiple orders (batch when supported)."""
    if not order_ids:
        return []
    if len(order_ids) == 1:
        return [cancel_order_id(client, order_ids[0])]
    resp = client.cancel_orders(order_ids)
    if isinstance(resp, dict) and (resp.get("error") or resp.get("success") is False):
        raise LiveClobPostError(str(resp.get("error") or resp))
    return resp if isinstance(resp, list) else [resp]


def cancel_market_asset(client: Any, *, condition_id: str, asset_id: str) -> dict[str, Any]:
    """Cancel all open orders for a market asset."""
    resp = client.cancel_market_orders(market=condition_id, asset_id=asset_id)
    if isinstance(resp, dict) and (resp.get("error") or resp.get("success") is False):
        raise LiveClobPostError(str(resp.get("error") or resp))
    return resp if isinstance(resp, dict) else {"response": resp}
