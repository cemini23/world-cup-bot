"""Gamma discovery for in-play match markets (Module 8 — shock recovery)."""

from __future__ import annotations

import json
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from world_cup_bot import scanner
from world_cup_bot.match_shock import slug_in_scope
from world_cup_bot.match_shock_config import MatchShockConfig, load_match_shock_config
from world_cup_bot.trading_mode import MarketKind, infer_market_kind_from_slug

DEFAULT_SEARCH_QUERIES = (
    "fifwc",
    "mexico south africa",
    "fifa world cup beat",
    "2026 world cup beat",
    "world cup beat",
    "epl beat",
    "champions league beat",
    "la liga beat",
    "international friendly beat",
)


@dataclass(frozen=True)
class MatchMarket:
    slug: str
    question: str
    condition_id: str
    yes_token_id: str
    no_token_id: str
    event_slug: str
    search_query: str
    accepting_orders: bool

    @property
    def yes_asset_id(self) -> str:
        return self.yes_token_id


def _parse_token_ids(market: dict[str, Any]) -> tuple[str, str]:
    raw = market.get("clobTokenIds") or market.get("clob_token_ids")
    if isinstance(raw, str):
        ids = json.loads(raw)
    elif isinstance(raw, list):
        ids = raw
    else:
        ids = []
    if len(ids) < 2:
        return "", ""
    return str(ids[0]), str(ids[1])


def parse_match_market(
    market: dict[str, Any],
    *,
    event_slug: str = "",
    search_query: str = "",
) -> MatchMarket | None:
    slug = str(market.get("slug") or "").strip()
    if not slug:
        return None
    if infer_market_kind_from_slug(slug) != MarketKind.MATCH:
        return None
    condition_id = str(market.get("conditionId") or market.get("condition_id") or "")
    yes_id, no_id = _parse_token_ids(market)
    if not condition_id or not yes_id:
        return None
    return MatchMarket(
        slug=slug,
        question=str(market.get("question") or ""),
        condition_id=condition_id,
        yes_token_id=yes_id,
        no_token_id=no_id,
        event_slug=event_slug or str(market.get("eventSlug") or ""),
        search_query=search_query,
        accepting_orders=bool(market.get("acceptingOrders", market.get("accepting_orders", True))),
    )


def discover_match_markets(
    gamma_url: str,
    *,
    cfg: MatchShockConfig | None = None,
    search_queries: tuple[str, ...] = DEFAULT_SEARCH_QUERIES,
    opener: Any | None = None,
) -> list[MatchMarket]:
    """Fetch match win / beat markets from Gamma public-search."""
    shock_cfg = cfg or load_match_shock_config()
    seen: set[str] = set()
    out: list[MatchMarket] = []

    for query in search_queries:
        try:
            payload = scanner.fetch_search_payload(gamma_url, query, opener=opener)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        for event in payload.get("events") or []:
            event_slug = str(event.get("slug") or "")
            for market in event.get("markets") or []:
                slug = str(market.get("slug") or "")
                if not slug_in_scope(slug, shock_cfg):
                    continue
                parsed = parse_match_market(
                    market,
                    event_slug=event_slug,
                    search_query=query,
                )
                if parsed is None:
                    continue
                key = parsed.condition_id.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(parsed)

    out.sort(key=lambda m: (m.search_query, m.slug))
    return out


def write_discovery_json(markets: list[MatchMarket], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "slug": m.slug,
            "question": m.question,
            "condition_id": m.condition_id,
            "yes_token_id": m.yes_token_id,
            "no_token_id": m.no_token_id,
            "event_slug": m.event_slug,
            "search_query": m.search_query,
            "accepting_orders": m.accepting_orders,
        }
        for m in markets
    ]
    path.write_text(json.dumps({"markets": rows}, indent=2), encoding="utf-8")


def load_discovery_json(path: Path) -> list[MatchMarket]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("markets") if isinstance(payload, dict) else payload
    out: list[MatchMarket] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        out.append(
            MatchMarket(
                slug=str(row["slug"]),
                question=str(row.get("question") or ""),
                condition_id=str(row["condition_id"]),
                yes_token_id=str(row["yes_token_id"]),
                no_token_id=str(row.get("no_token_id") or ""),
                event_slug=str(row.get("event_slug") or ""),
                search_query=str(row.get("search_query") or ""),
                accepting_orders=bool(row.get("accepting_orders", True)),
            )
        )
    return out
