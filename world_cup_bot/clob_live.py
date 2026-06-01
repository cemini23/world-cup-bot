"""Live CLOB order POST via py-clob-client-v2 (optional [live] extra)."""

from __future__ import annotations

import os
from typing import Any

from world_cup_bot.config import Settings
from world_cup_bot.fill_handler import ExitIntent
from world_cup_bot.quoter import QuoteIntent

_V2_IMPORT_ERROR = (
    "pip install -e '.[live]' for live CLOB POST "
    "(py-clob-client-v2 required after Apr 2026 cutover)"
)
_VERSION_MISMATCH_HINT = (
    "order_version_mismatch — install py-clob-client-v2 (pip install -e '.[live]') "
    "and complete Polymarket Exchange V2 wallet migration"
)


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


def _builder_config() -> Any | None:
    from py_clob_client_v2.clob_types import BuilderConfig

    code = os.environ.get("POLYMARKET_BUILDER_CODE", "").strip()
    if not code:
        return None
    address = os.environ.get("POLYMARKET_BUILDER_ADDRESS", "").strip()
    if not address:
        address = os.environ.get("POLYMARKET_FUNDER_ADDRESS", "").strip()
    return BuilderConfig(builder_address=address, builder_code=code)


def _raise_post_error(exc: BaseException) -> None:
    from py_clob_client_v2.exceptions import PolyApiException

    if isinstance(exc, PolyApiException):
        msg = exc.error_msg
        if isinstance(msg, dict):
            text = str(msg.get("error") or msg)
        else:
            text = str(msg)
        if "order_version_mismatch" in text:
            raise LiveClobPostError(f"{text} — {_VERSION_MISMATCH_HINT}") from exc
        raise LiveClobPostError(text) from exc
    raise LiveClobPostError(str(exc)) from exc


def order_options_for_token(client: Any, token_id: str) -> Any:
    from py_clob_client_v2.clob_types import PartialCreateOrderOptions

    tick = client.get_tick_size(token_id)
    neg = client.get_neg_risk(token_id)
    return PartialCreateOrderOptions(tick_size=tick, neg_risk=neg)


def build_clob_client(settings: Settings) -> Any:
    """Return configured py-clob-client-v2 ClobClient."""
    try:
        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import ApiCreds
    except ImportError as exc:
        raise LiveClobNotConfiguredError(_V2_IMPORT_ERROR) from exc

    from world_cup_bot.clob_auth import load_clob_auth

    auth = load_clob_auth()
    creds = ApiCreds(
        api_key=auth.api_key,
        api_secret=auth.secret,
        api_passphrase=auth.passphrase,
    )
    funder = _funder_address()
    builder_config = _builder_config()
    kwargs: dict[str, Any] = {
        "host": settings.clob_url,
        "chain_id": 137,
        "key": _require_private_key(),
        "creds": creds,
        "signature_type": _signature_type(),
        "use_server_time": True,
        "retry_on_error": True,
    }
    if funder:
        kwargs["funder"] = funder
    if builder_config is not None:
        kwargs["builder_config"] = builder_config
    return ClobClient(**kwargs)


def _check_post_response(resp: dict[str, Any]) -> dict[str, Any]:
    if resp.get("error") or resp.get("success") is False:
        err = str(resp.get("error") or resp)
        if "order_version_mismatch" in err:
            raise LiveClobPostError(f"{err} — {_VERSION_MISMATCH_HINT}")
        raise LiveClobPostError(err)
    return resp


def post_quote_intent(client: Any, intent: QuoteIntent) -> dict[str, Any]:
    """Post resting limit bid (post-only GTC)."""
    from py_clob_client_v2.clob_types import OrderArgs
    from py_clob_client_v2.order_builder.constants import BUY

    order_args = OrderArgs(
        token_id=intent.token_id,
        price=intent.price,
        size=intent.size_shares,
        side=BUY,
    )
    options = order_options_for_token(client, intent.token_id)
    try:
        order = client.create_order(order_args, options)
        resp = client.post_order(order, post_only=True)
    except Exception as exc:
        _raise_post_error(exc)
    if not isinstance(resp, dict):
        return {"response": resp}
    return _check_post_response(resp)


def post_exit_intent(client: Any, intent: ExitIntent) -> dict[str, Any]:
    """Post resting limit sell to exit a fill (GTC, not post-only)."""
    from py_clob_client_v2.clob_types import OrderArgs
    from py_clob_client_v2.order_builder.constants import SELL

    order_args = OrderArgs(
        token_id=intent.token_id,
        price=intent.price,
        size=intent.size_shares,
        side=SELL,
    )
    options = order_options_for_token(client, intent.token_id)
    try:
        order = client.create_order(order_args, options)
        resp = client.post_order(order)
    except Exception as exc:
        _raise_post_error(exc)
    if not isinstance(resp, dict):
        return {"response": resp}
    return _check_post_response(resp)


def post_arb_order(
    client: Any,
    *,
    token_id: str,
    side: str,
    price: float,
    size_shares: float,
) -> dict[str, Any]:
    """Aggressive GTC limit for cross-venue hedge (not post-only)."""
    from py_clob_client_v2.clob_types import OrderArgs
    from py_clob_client_v2.order_builder.constants import BUY, SELL

    order_side = BUY if side.upper() == "BUY" else SELL
    order_args = OrderArgs(
        token_id=token_id,
        price=price,
        size=size_shares,
        side=order_side,
    )
    options = order_options_for_token(client, token_id)
    try:
        order = client.create_order(order_args, options)
        resp = client.post_order(order, post_only=False)
    except Exception as exc:
        _raise_post_error(exc)
    if not isinstance(resp, dict):
        return {"response": resp}
    return _check_post_response(resp)


class LivePmArbClient:
    """Thin adapter for cross_venue_exec.PmArbClient."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def post_arb_order(
        self,
        *,
        token_id: str,
        side: str,
        price: float,
        size_shares: float,
        dry_run: bool,
    ) -> dict[str, Any]:
        if dry_run:
            return {"orderID": f"dry-pm-{token_id[:8]}", "status": "dry_run"}
        return post_arb_order(
            self._client,
            token_id=token_id,
            side=side,
            price=price,
            size_shares=size_shares,
        )


def cancel_order_id(client: Any, order_id: str) -> dict[str, Any]:
    """Cancel one resting order by id."""
    from py_clob_client_v2.clob_types import OrderPayload

    try:
        resp = client.cancel_order(OrderPayload(orderID=order_id))
    except Exception as exc:
        _raise_post_error(exc)
    if isinstance(resp, dict) and (resp.get("error") or resp.get("success") is False):
        raise LiveClobPostError(str(resp.get("error") or resp))
    return resp if isinstance(resp, dict) else {"response": resp}


def cancel_order_ids(client: Any, order_ids: list[str]) -> list[dict[str, Any]]:
    """Cancel multiple orders (batch when supported)."""
    if not order_ids:
        return []
    if len(order_ids) == 1:
        return [cancel_order_id(client, order_ids[0])]
    try:
        resp = client.cancel_orders(order_ids)
    except Exception as exc:
        _raise_post_error(exc)
    if isinstance(resp, dict) and (resp.get("error") or resp.get("success") is False):
        raise LiveClobPostError(str(resp.get("error") or resp))
    return resp if isinstance(resp, list) else [resp]


def cancel_market_asset(client: Any, *, condition_id: str, asset_id: str) -> dict[str, Any]:
    """Cancel all open orders for a market asset."""
    from py_clob_client_v2.clob_types import OrderMarketCancelParams

    payload = OrderMarketCancelParams(market=condition_id, asset_id=asset_id)
    try:
        resp = client.cancel_market_orders(payload)
    except Exception as exc:
        _raise_post_error(exc)
    if isinstance(resp, dict) and (resp.get("error") or resp.get("success") is False):
        raise LiveClobPostError(str(resp.get("error") or resp))
    return resp if isinstance(resp, dict) else {"response": resp}
