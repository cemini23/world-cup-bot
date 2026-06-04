"""Order-time policy checks from operating.yaml wiki invariants.

Opt-in via WC_WIKI_ENFORCEMENT=1.
"""

from __future__ import annotations

from world_cup_bot import calendar_guard
from world_cup_bot.config import Settings, wiki_enforcement_enabled
from world_cup_bot.operating_config import OperatingConfig
from world_cup_bot.quoter import QuoteIntent
from world_cup_bot.scanner import AdvanceMarket


class WikiEnforcementError(RuntimeError):
    """Raised when an intent violates wiki operating rules."""


def check_intents(
    intents: list[QuoteIntent],
    settings: Settings,
    markets: list[AdvanceMarket],
    operating: OperatingConfig,
) -> list[str]:
    """Return violation messages; empty when all intents pass."""
    if not wiki_enforcement_enabled():
        return []

    market_by_team = {m.team: m for m in markets}
    in_window = {
        team
        for team, _ in calendar_guard.teams_in_cancel_window(
            min_hours_before_kickoff=settings.min_hours_before_kickoff
        )
    }
    cap = settings.max_notional_per_market_usd
    high_mid = operating.bilateral.high_mid

    violations: list[str] = []
    for intent in intents:
        if intent.notional_usd > cap + 1e-6:
            violations.append(
                f"{intent.team} {intent.side}: notional ${intent.notional_usd:.2f} > cap ${cap:.2f}"
            )
        if intent.team in in_window:
            violations.append(f"{intent.team}: inside calendar cancel window — no new quotes")

        market = market_by_team.get(intent.team)
        if market and market.mid is not None and market.mid >= high_mid and intent.side == "YES":
            has_no = any(
                i.team == intent.team and i.side == "NO" for i in intents if i is not intent
            )
            if not has_no:
                violations.append(
                    f"{intent.team}: YES-only at mid {market.mid:.3f} >= {high_mid} "
                    "— bilateral wiki requires NO leg"
                )

    return violations


def enforce_or_raise(
    intents: list[QuoteIntent],
    settings: Settings,
    markets: list[AdvanceMarket],
    operating: OperatingConfig,
) -> None:
    violations = check_intents(intents, settings, markets, operating)
    if violations:
        raise WikiEnforcementError("; ".join(violations))
