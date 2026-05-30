"""Dual-validation settlement gates — block FSM exit until phase markets resolve (DR 10)."""

from __future__ import annotations

import json
import re
import urllib.error
from dataclasses import dataclass
from typing import Any

from world_cup_bot.market_phases import MarketPhasesConfig, MarketPhaseSpec
from world_cup_bot.scanner import fetch_search_payload


@dataclass(frozen=True)
class PhaseSettlementStatus:
    phase_id: str
    total_markets: int
    settled_markets: int

    @property
    def all_settled(self) -> bool:
        if self.total_markets == 0:
            return True
        return self.settled_markets >= self.total_markets


@dataclass(frozen=True)
class SettlementGateReport:
    by_phase: dict[str, PhaseSettlementStatus]
    pending_phase_ids: tuple[str, ...]

    def phase_status(self, phase_id: str) -> PhaseSettlementStatus | None:
        return self.by_phase.get(phase_id)


def _parse_json_field(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    return list(raw)


def market_is_settled(market: dict[str, Any]) -> bool:
    """True when Gamma indicates the market is no longer open for trading."""
    if market.get("closed") is True:
        return True
    if market.get("acceptingOrders") is False:
        return True
    prices = _parse_json_field(market.get("outcomePrices"))
    if prices and len(prices) >= 2:
        try:
            p0, p1 = float(prices[0]), float(prices[1])
            if p0 >= 0.999 or p1 >= 0.999 or p0 <= 0.001 or p1 <= 0.001:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _match_phase(question: str, spec: MarketPhaseSpec) -> bool:
    if not spec.title_regex:
        return False
    return re.match(spec.title_regex, question.strip(), re.IGNORECASE) is not None


def _markets_for_phase(
    payload: dict[str, Any],
    spec: MarketPhaseSpec,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in payload.get("events") or []:
        for market in event.get("markets") or []:
            question = str(market.get("question") or "")
            if _match_phase(question, spec):
                out.append(market)
    return out


def check_phase_settlement(
    config: MarketPhasesConfig,
    phase_id: str,
    *,
    gamma_url: str = "https://gamma-api.polymarket.com",
    opener: Any | None = None,
    payloads_by_query: dict[str, dict[str, Any]] | None = None,
) -> PhaseSettlementStatus:
    spec = config.phases.get(phase_id)
    if spec is None or not spec.title_regex:
        return PhaseSettlementStatus(phase_id=phase_id, total_markets=0, settled_markets=0)

    query = spec.gamma_search or "world cup"
    cache = payloads_by_query if payloads_by_query is not None else {}
    payload = cache.get(query)
    if payload is None:
        try:
            payload = fetch_search_payload(gamma_url, query, opener=opener)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return PhaseSettlementStatus(phase_id=phase_id, total_markets=0, settled_markets=0)
        cache[query] = payload

    markets = _markets_for_phase(payload, spec)
    settled = sum(1 for m in markets if market_is_settled(m))
    return PhaseSettlementStatus(
        phase_id=phase_id,
        total_markets=len(markets),
        settled_markets=settled,
    )


def check_phases_settlement(
    config: MarketPhasesConfig,
    phase_ids: list[str],
    *,
    gamma_url: str = "https://gamma-api.polymarket.com",
    opener: Any | None = None,
) -> SettlementGateReport:
    cache: dict[str, dict[str, Any]] = {}
    by_phase: dict[str, PhaseSettlementStatus] = {}
    for pid in phase_ids:
        by_phase[pid] = check_phase_settlement(
            config,
            pid,
            gamma_url=gamma_url,
            opener=opener,
            payloads_by_query=cache,
        )
    pending = tuple(
        pid for pid, st in by_phase.items() if st.total_markets > 0 and not st.all_settled
    )
    return SettlementGateReport(by_phase=by_phase, pending_phase_ids=pending)
