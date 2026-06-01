"""Scale quote intents to available USDC collateral (live plan only)."""

from __future__ import annotations

import logging
import os
from dataclasses import replace

from world_cup_bot.config import Settings
from world_cup_bot.quoter import QuoteIntent, _shares_for_notional

logger = logging.getLogger(__name__)


def cap_to_collateral_enabled() -> bool:
    raw = os.environ.get("WC_CAP_TO_COLLATERAL", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def fetch_collateral_balance_usd(settings: Settings) -> float:
    """USDC.e balance for the configured CLOB funder (proxy when sig type 1/2)."""
    from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams

    from world_cup_bot.clob_live import LiveClobNotConfiguredError, build_clob_client

    try:
        client = build_clob_client(settings)
    except LiveClobNotConfiguredError as exc:
        raise RuntimeError(f"balance fetch: {exc}") from exc

    sig_type = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE", "0"))
    ba = client.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=sig_type)
    )
    return int(ba["balance"]) / 1_000_000


def _scaled_intents(intents: list[QuoteIntent], scale: float) -> list[QuoteIntent]:
    out: list[QuoteIntent] = []
    for intent in intents:
        target = intent.notional_usd * scale
        shares = _shares_for_notional(
            target, intent.price, intent.snapshot.rewards_min_shares
        )
        notional = round(shares * intent.price, 4)
        out.append(
            replace(intent, size_shares=shares, notional_usd=notional)
        )
    return out


def cap_intents_to_collateral(
    intents: list[QuoteIntent],
    budget_usd: float,
) -> list[QuoteIntent]:
    """Proportionally scale intents so total BUY collateral stays within budget."""
    if not intents or budget_usd <= 0:
        return []

    total = sum(i.notional_usd for i in intents)
    if total <= budget_usd:
        return intents

    lo, hi = 0.0, 1.0
    best: list[QuoteIntent] = []
    for _ in range(48):
        mid = (lo + hi) / 2
        scaled = _scaled_intents(intents, mid)
        used = sum(i.notional_usd for i in scaled)
        if used <= budget_usd:
            best = scaled
            lo = mid
        else:
            hi = mid

    if not best:
        logger.warning(
            "balance cap: no intents fit within $%.2f (requested $%.2f)",
            budget_usd,
            total,
        )
        return []

    used = sum(i.notional_usd for i in best)
    logger.info(
        "balance cap: scaled %d intents $%.2f → $%.2f (budget $%.2f, scale %.3f)",
        len(best),
        total,
        used,
        budget_usd,
        lo,
    )
    return best


def cap_intents_to_available_collateral(
    intents: list[QuoteIntent],
    settings: Settings,
) -> list[QuoteIntent]:
    """Fetch live collateral and scale intents to fit."""
    reserve = float(os.environ.get("WC_COLLATERAL_RESERVE_USD", "0") or "0")
    balance = fetch_collateral_balance_usd(settings)
    budget = max(0.0, balance - reserve)
    logger.info("collateral balance $%.2f reserve $%.2f budget $%.2f", balance, reserve, budget)
    return cap_intents_to_collateral(intents, budget)
