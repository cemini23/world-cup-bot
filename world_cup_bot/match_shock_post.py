"""Live ladder POST for Module 8 — isolated from advance-LP order manager."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from world_cup_bot.clob_live import (
    LiveClobNotConfiguredError,
    LiveClobPostError,
    _check_post_response,
    build_clob_client,
)
from world_cup_bot.config import (
    Settings,
    match_shock_enabled,
    match_shock_live,
    match_shock_live_ack,
)
from world_cup_bot.match_shock import LadderPlan
from world_cup_bot.match_shock_config import MatchShockConfig, load_match_shock_config
from world_cup_bot.match_shock_ledger import record_live_post


@dataclass(frozen=True)
class ShockLadderIntent:
    token_id: str
    slug: str
    limit_price: float
    size_usd: float
    percentile: int
    ttl_ms: int


@dataclass(frozen=True)
class LivePostGateResult:
    allowed: bool
    reason: str


def check_live_post_gates(
    settings: Settings,
    cfg: MatchShockConfig | None = None,
    *,
    test_auth: bool = False,
) -> LivePostGateResult:
    """Gate live ladder POST — same v2 CLOB stack as LP quoter; no geoblock API gate."""
    shock_cfg = cfg or load_match_shock_config()
    if not shock_cfg.enabled:
        return LivePostGateResult(False, "shock_match.yaml enabled=false")
    if not match_shock_enabled():
        return LivePostGateResult(False, "WC_SHOCK_ENABLED not set")
    if not match_shock_live():
        return LivePostGateResult(False, "WC_MATCH_SHOCK_LIVE not set")
    if settings.dry_run:
        return LivePostGateResult(False, "DRY_RUN=true")
    if not match_shock_live_ack():
        return LivePostGateResult(False, "WC_MATCH_SHOCK_LIVE_ACK not set")

    pk = os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip()
    if not pk:
        return LivePostGateResult(False, "POLYMARKET_PRIVATE_KEY missing")

    try:
        import py_clob_client_v2  # noqa: F401
    except ImportError:
        return LivePostGateResult(False, "pip install -e '.[live]' (py-clob-client-v2)")

    if test_auth:
        from world_cup_bot.clob_auth import MissingClobAuthError, load_clob_auth
        from world_cup_bot.clob_rest import fetch_open_orders

        try:
            auth = load_clob_auth()
        except MissingClobAuthError as exc:
            return LivePostGateResult(False, str(exc))

        poly = os.environ.get("POLYMARKET_POLY_ADDRESS", "").strip()
        if poly:
            try:
                fetch_open_orders(settings.clob_url, auth, poly, max_pages=1)
            except Exception as exc:
                return LivePostGateResult(False, f"L2 auth / orders failed: {exc}")

    return LivePostGateResult(True, "gates pass (py-clob-client-v2)")


def ladder_to_intents(
    plan: LadderPlan,
    *,
    token_id: str,
    slug: str,
    ttl_ms: int,
) -> tuple[ShockLadderIntent, ...]:
    intents: list[ShockLadderIntent] = []
    for order in plan.orders:
        intents.append(
            ShockLadderIntent(
                token_id=token_id,
                slug=slug,
                limit_price=order.limit_price,
                size_usd=order.size_usd,
                percentile=order.percentile,
                ttl_ms=ttl_ms,
            )
        )
    return tuple(intents)


def _shares_for_notional(price: float, notional_usd: float) -> float:
    if price <= 0:
        return 0.0
    return notional_usd / price


def post_shock_ladder_order(client: Any, intent: ShockLadderIntent) -> dict[str, Any]:
    """Post resting limit bid (GTC, post-only) for one ladder rung."""
    from py_clob_client_v2.clob_types import OrderArgs
    from py_clob_client_v2.order_builder.constants import BUY

    from world_cup_bot.clob_live import order_options_for_token

    size_shares = _shares_for_notional(intent.limit_price, intent.size_usd)
    order_args = OrderArgs(
        token_id=intent.token_id,
        price=intent.limit_price,
        size=size_shares,
        side=BUY,
    )
    options = order_options_for_token(client, intent.token_id)
    try:
        order = client.create_order(order_args, options)
        resp = client.post_order(order, post_only=True)
    except Exception as exc:
        from world_cup_bot.clob_live import _raise_post_error

        _raise_post_error(exc)
    if not isinstance(resp, dict):
        return {"response": resp}
    return _check_post_response(resp)


def submit_ladder(
    plan: LadderPlan,
    *,
    token_id: str,
    slug: str,
    settings: Settings,
    cfg: MatchShockConfig | None = None,
    ledger_path: str | Path | None = None,
    dry_run: bool = True,
    test_auth: bool = False,
) -> list[dict[str, Any]]:
    shock_cfg = cfg or load_match_shock_config()
    intents = ladder_to_intents(
        plan,
        token_id=token_id,
        slug=slug,
        ttl_ms=shock_cfg.ladder.order_ttl_ms,
    )
    if dry_run:
        return [
            {
                "dry_run": True,
                "slug": i.slug,
                "percentile": i.percentile,
                "limit_price": i.limit_price,
                "size_usd": i.size_usd,
            }
            for i in intents
        ]

    gate = check_live_post_gates(settings, shock_cfg, test_auth=test_auth)
    if not gate.allowed:
        raise LiveClobPostError(f"live POST blocked: {gate.reason}")

    try:
        client = build_clob_client(settings)
    except LiveClobNotConfiguredError as exc:
        raise LiveClobPostError(str(exc)) from exc

    results: list[dict[str, Any]] = []
    ledger = Path(ledger_path) if ledger_path else None
    for intent in intents:
        resp = post_shock_ladder_order(client, intent)
        order_id = str(resp.get("orderID") or resp.get("order_id") or "")
        row = {
            "order_id": order_id,
            "slug": slug,
            "percentile": intent.percentile,
            "limit_price": intent.limit_price,
            "size_usd": intent.size_usd,
            "response": resp,
        }
        results.append(row)
        if ledger and order_id:
            record_live_post(
                ledger,
                slug=slug,
                plan=plan,
                order_id=order_id,
                limit_price=intent.limit_price,
                size_usd=intent.size_usd,
                percentile=intent.percentile,
            )
    return results
