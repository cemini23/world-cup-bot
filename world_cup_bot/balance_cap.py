"""Scale quote intents to available USDC collateral (live plan only)."""

from __future__ import annotations

import logging
import os
from dataclasses import replace

from world_cup_bot.config import Settings
from world_cup_bot.order_manager import OpenOrder, fetch_wc_open_orders
from world_cup_bot.quoter import QuoteIntent, _shares_for_notional
from world_cup_bot.scanner import AdvanceMarket

logger = logging.getLogger(__name__)


def cap_to_collateral_enabled(*, dry_run: bool = True) -> bool:
    raw = os.environ.get("WC_CAP_TO_COLLATERAL", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return not dry_run


def fetch_collateral_balance_usd(settings: Settings) -> float:
    """USDC.e balance for the configured CLOB funder (proxy when sig type 1/2)."""
    from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams

    from world_cup_bot.clob_live import LiveClobNotConfiguredError, build_clob_client

    try:
        client = build_clob_client(settings)
    except LiveClobNotConfiguredError as exc:
        raise RuntimeError(f"balance fetch: {exc}") from exc

    sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "2"))
    ba = client.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=sig_type)
    )
    return int(ba["balance"]) / 1_000_000


def _min_collateral(intent: QuoteIntent) -> float:
    return intent.snapshot.rewards_min_shares * intent.price


def _intent_at_notional(intent: QuoteIntent, notional_usd: float) -> QuoteIntent:
    shares = _shares_for_notional(notional_usd, intent.price, intent.snapshot.rewards_min_shares)
    return replace(intent, size_shares=shares, notional_usd=round(shares * intent.price, 4))


def cap_intents_to_collateral(
    intents: list[QuoteIntent],
    budget_usd: float,
) -> list[QuoteIntent]:
    """Fit intents within budget, respecting rewards min_shares per leg."""
    if not intents or budget_usd <= 0:
        return []

    original_notional = {i.order_id: i.notional_usd for i in intents}
    total = sum(i.notional_usd for i in intents)
    if total <= budget_usd:
        return intents

    # Greedy pack: cheapest min-collateral legs first (max coverage on small wallets).
    remaining = budget_usd
    selected: list[QuoteIntent] = []
    for intent in sorted(intents, key=_min_collateral):
        floor = _min_collateral(intent)
        if floor > remaining + 0.01:
            continue
        placed = _intent_at_notional(intent, floor)
        selected.append(placed)
        remaining -= placed.notional_usd

    if not selected:
        logger.warning(
            "balance cap: no intents fit within $%.2f (requested $%.2f)",
            budget_usd,
            total,
        )
        return []

    # Spread leftover budget evenly across selected legs (still honoring min_shares).
    if remaining > 0.05:
        extra_each = remaining / len(selected)
        selected = [
            _intent_at_notional(
                i,
                min(
                    i.notional_usd + extra_each,
                    original_notional.get(i.order_id, i.notional_usd),
                ),
            )
            for i in selected
        ]

    used = sum(i.notional_usd for i in selected)
    logger.info(
        "balance cap: kept %d/%d intents $%.2f → $%.2f (budget $%.2f)",
        len(selected),
        len(intents),
        total,
        used,
        budget_usd,
    )
    return selected


def _open_buy_collateral_usd(orders: list[OpenOrder]) -> float:
    return sum(o.price * o.size for o in orders if o.side == "BUY")


def fetch_account_bankroll_usd(settings: Settings) -> float:
    """PM account bankroll: free USDC collateral + resting BUY order lock."""
    from world_cup_bot.clob_auth import load_clob_auth, load_poly_address
    from world_cup_bot.clob_rest import fetch_open_orders

    balance = fetch_collateral_balance_usd(settings)
    auth = load_clob_auth()
    address = load_poly_address()
    raw_orders = fetch_open_orders(settings.clob_url, auth, address, max_pages=5)
    locked = 0.0
    for row in raw_orders:
        if str(row.get("side", "")).upper() != "BUY":
            continue
        try:
            price = float(row.get("price") or 0)
            size = float(row.get("size") or row.get("original_size") or 0)
        except (TypeError, ValueError):
            continue
        locked += price * size
    return round(balance + locked, 2)


def _collateral_locked_outside_intents(
    open_orders: list[OpenOrder],
    intents: list[QuoteIntent],
) -> float:
    """USDC tied up in resting orders we are not about to cancel-replace."""
    refresh_assets = {i.token_id for i in intents}
    locked = 0.0
    for order in open_orders:
        if order.side != "BUY":
            continue
        if order.asset_id in refresh_assets:
            continue
        locked += order.price * order.size
    return locked


def subtract_open_orders_enabled() -> bool:
    raw = os.environ.get("WC_CAP_SUBTRACT_OPEN_ORDERS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def cap_intents_to_available_collateral(
    intents: list[QuoteIntent],
    settings: Settings,
    *,
    markets: list[AdvanceMarket] | None = None,
) -> list[QuoteIntent]:
    """Fetch live collateral and scale intents to fit."""
    reserve = float(os.environ.get("WC_COLLATERAL_RESERVE_USD", "2") or "0")
    balance = fetch_collateral_balance_usd(settings)
    budget = max(0.0, balance - reserve)
    locked = 0.0
    if subtract_open_orders_enabled() and markets and not settings.dry_run:
        try:
            open_orders = fetch_wc_open_orders(settings, markets)
            locked = _collateral_locked_outside_intents(open_orders, intents)
            budget = max(0.0, budget - locked)
            open_total = _open_buy_collateral_usd(open_orders)
            logger.info(
                "open orders $%.2f locked-outside-intents $%.2f",
                open_total,
                locked,
            )
        except Exception as exc:
            if settings.dry_run:
                logger.warning("open-order collateral subtract skipped: %s", exc)
            else:
                raise RuntimeError(
                    f"open-order collateral subtract failed (refusing live cap): {exc}"
                ) from exc
    logger.info(
        "collateral balance $%.2f reserve $%.2f locked $%.2f budget $%.2f",
        balance,
        reserve,
        locked,
        budget,
    )
    return cap_intents_to_collateral(intents, budget)
