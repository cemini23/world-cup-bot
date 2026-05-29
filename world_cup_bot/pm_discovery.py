"""Polymarket discovery for Module 6 — group winner, advance, and future slug patterns."""

from __future__ import annotations

import json
import re
import urllib.error
from dataclasses import dataclass
from typing import Any

from world_cup_bot import scanner, team_names

_GROUP_WINNER = re.compile(
    r"^Will (.+?) win Group ([A-L]) in the 2026 FIFA World Cup\??$",
    re.IGNORECASE,
)
# Legacy / alternate group-winner wording if PM rephrases
_GROUP_WINNER_ALT = re.compile(
    r"^Will (.+?) win Group ([A-L])\??$",
    re.IGNORECASE,
)
# Alternate advance phrasing as PM slugs evolve
_ADVANCE_ALT = re.compile(
    r"^Will (.+?) (?:advance|qualify) (?:to|for) (?:the )?"
    r"(?:knockout|Round of 32|round of 32).*2026.*World Cup",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PolymarketSnapshot:
    team: str
    market_type: str
    group: str | None
    question: str
    slug: str
    condition_id: str
    mid: float | None
    best_bid: float | None
    best_ask: float | None
    volume: float | None
    liquidity: float | None
    accepting_orders: bool
    search_query: str | None = None

    @property
    def pair_key(self) -> str:
        return f"{self.market_type}:{self.team}"


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _mid_from_market(market: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    bid = _optional_float(market.get("bestBid"))
    ask = _optional_float(market.get("bestAsk"))
    mid = None
    if bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
    elif market.get("outcomePrices"):
        raw = market.get("outcomePrices")
        if isinstance(raw, str):
            prices = json.loads(raw)
        else:
            prices = list(raw)
        if prices:
            mid = float(prices[0])
    return mid, bid, ask


def parse_group_winner_market(
    market: dict[str, Any], *, search_query: str | None = None
) -> PolymarketSnapshot | None:
    question = (market.get("question") or "").strip()
    m = _GROUP_WINNER.match(question) or _GROUP_WINNER_ALT.match(question)
    if not m:
        return None
    team = team_names.normalize_team(m.group(1))
    group = m.group(2).upper()
    mid, bid, ask = _mid_from_market(market)
    return PolymarketSnapshot(
        team=team,
        market_type="group_winner",
        group=group,
        question=question,
        slug=str(market.get("slug") or ""),
        condition_id=str(market.get("conditionId") or ""),
        mid=mid,
        best_bid=bid,
        best_ask=ask,
        volume=_optional_float(market.get("volume")),
        liquidity=_optional_float(market.get("liquidity")),
        accepting_orders=bool(market.get("acceptingOrders")),
        search_query=search_query,
    )


def parse_advance_market(
    market: dict[str, Any],
    *,
    search_query: str | None = None,
) -> PolymarketSnapshot | None:
    question = (market.get("question") or "").strip()
    team = scanner.parse_team_from_question(question)
    market_type = "advance_to_knockout"
    if not team:
        m = _ADVANCE_ALT.match(question)
        if not m:
            return None
        team = team_names.normalize_team(m.group(1))
    mid, bid, ask = _mid_from_market(market)
    return PolymarketSnapshot(
        team=team,
        market_type=market_type,
        group=None,
        question=question,
        slug=str(market.get("slug") or ""),
        condition_id=str(market.get("conditionId") or ""),
        mid=mid,
        best_bid=bid,
        best_ask=ask,
        volume=_optional_float(market.get("volume")),
        liquidity=_optional_float(market.get("liquidity")),
        accepting_orders=bool(market.get("acceptingOrders")),
        search_query=search_query,
    )


def parse_any_wc_market(
    market: dict[str, Any], *, search_query: str | None = None
) -> PolymarketSnapshot | None:
    return parse_group_winner_market(market, search_query=search_query) or parse_advance_market(
        market, search_query=search_query
    )


def fetch_search_payload(
    gamma_url: str,
    query: str,
    *,
    opener: Any | None = None,
) -> dict[str, Any]:
    return scanner.fetch_search_payload(gamma_url, query, opener=opener)


def discover_polymarket_markets(
    gamma_url: str = "https://gamma-api.polymarket.com",
    *,
    search_queries: tuple[str, ...] | None = None,
    opener: Any | None = None,
) -> list[PolymarketSnapshot]:
    """Merge Gamma public-search results; dedupe by condition_id."""
    queries = search_queries or (
        "win Group",
        "world cup group winner",
        "world cup advance knockout",
        "2026 FIFA World Cup",
    )
    by_cid: dict[str, PolymarketSnapshot] = {}

    for query in queries:
        try:
            payload = fetch_search_payload(gamma_url, query, opener=opener)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        for event in payload.get("events") or []:
            for market in event.get("markets") or []:
                parsed = parse_any_wc_market(market, search_query=query)
                if not parsed or not parsed.condition_id:
                    continue
                by_cid[parsed.condition_id] = parsed

    out = sorted(by_cid.values(), key=lambda m: (m.market_type, m.team.lower()))
    return out


def index_polymarket_markets(markets: list[PolymarketSnapshot]) -> dict[str, PolymarketSnapshot]:
    """Index by pair_key (market_type:team); latest slug wins on duplicate."""
    idx: dict[str, PolymarketSnapshot] = {}
    for m in markets:
        idx[m.pair_key] = m
    return idx


def index_polymarket_by_slug(markets: list[PolymarketSnapshot]) -> dict[str, PolymarketSnapshot]:
    return {m.slug: m for m in markets if m.slug}


def match_polymarket_for_pair(
    *,
    team: str,
    market_type: str,
    hint: str,
    catalog: dict[str, PolymarketSnapshot],
    markets: list[PolymarketSnapshot],
    polymarket_slug: str | None = None,
    slug_index: dict[str, PolymarketSnapshot] | None = None,
) -> PolymarketSnapshot | None:
    """Resolve PM market for a config pair — slug, hint, then team key."""
    if polymarket_slug and slug_index and polymarket_slug in slug_index:
        return slug_index[polymarket_slug]

    if polymarket_slug:
        for m in markets:
            if m.slug == polymarket_slug:
                return m

    hint_lower = hint.lower().strip()
    if hint_lower:
        for m in markets:
            if m.question.lower() == hint_lower:
                return m
        for m in markets:
            if hint_lower in m.question.lower():
                return m

    key = f"{market_type}:{team_names.normalize_team(team)}"
    if key in catalog:
        return catalog[key]

    norm = team_names.normalize_team(team)
    for m in markets:
        if m.market_type == market_type and team_names.teams_match(m.team, norm):
            return m
    return None
