"""Load Module 6 cross-venue scanner config from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CROSS_VENUE = Path(__file__).resolve().parent.parent / "config" / "cross_venue.yaml"


@dataclass(frozen=True)
class DiscoveryConfig:
    kalshi_ticker_prefixes: tuple[str, ...]
    polymarket_search_queries: tuple[str, ...]
    rules_hash_by_market_type: dict[str, str]
    blocked_market_types: frozenset[str]


@dataclass(frozen=True)
class CrossVenuePair:
    team: str
    market_type: str
    polymarket_hint: str
    kalshi_event_ticker: str
    kalshi_market_ticker: str
    rules_hash: str
    enabled: bool
    last_verified: str | None
    notes: str | None
    polymarket_slug: str | None = None
    polymarket_condition_id: str | None = None

    @property
    def pair_key(self) -> str:
        return f"{self.market_type}:{self.team}"


@dataclass(frozen=True)
class CrossVenueConfig:
    version: int
    alert_threshold_pp: float
    poll_interval_sec: float
    fee_kalshi_profit_pct: float
    verification_max_age_days: int
    pairs: tuple[CrossVenuePair, ...]
    blockers: tuple[str, ...]
    discovery: DiscoveryConfig


def load_cross_venue_config(path: Path | None = None) -> CrossVenueConfig:
    p = path or DEFAULT_CROSS_VENUE
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    disc = raw.get("discovery") or {}
    rules_map = disc.get("rules_hash_by_market_type") or {
        "group_winner": "group_winner_fifa_tiebreak_v1",
        "advance_to_knockout": "advance_knockout_v1",
        "group_qualify": "group_qualify_v1",
    }
    discovery = DiscoveryConfig(
        kalshi_ticker_prefixes=tuple(
            disc.get("kalshi_ticker_prefixes")
            or ("KXWCGROUPWIN", "KXWCGROUPQUAL", "KXWCROUND", "KXWCGAME")
        ),
        polymarket_search_queries=tuple(
            disc.get("polymarket_search_queries")
            or (
                "win Group",
                "world cup group winner",
                "world cup advance knockout",
                "2026 FIFA World Cup",
            )
        ),
        rules_hash_by_market_type={str(k): str(v) for k, v in rules_map.items()},
        blocked_market_types=frozenset(
            disc.get("blocked_market_types") or ("group_qualify", "round_of_16_qualify")
        ),
    )

    pairs: list[CrossVenuePair] = []
    for row in raw.get("pairs") or []:
        pairs.append(
            CrossVenuePair(
                team=str(row["team"]),
                market_type=str(row.get("market_type", "group_winner")),
                polymarket_hint=str(row.get("polymarket_hint") or ""),
                kalshi_event_ticker=str(row.get("kalshi_event_ticker") or ""),
                kalshi_market_ticker=str(row.get("kalshi_market_ticker") or ""),
                rules_hash=str(row.get("rules_hash") or ""),
                enabled=bool(row.get("enabled", True)),
                last_verified=row.get("last_verified"),
                notes=row.get("notes"),
                polymarket_slug=row.get("polymarket_slug"),
                polymarket_condition_id=row.get("polymarket_condition_id"),
            )
        )

    return CrossVenueConfig(
        version=int(raw.get("version", 1)),
        alert_threshold_pp=float(raw.get("alert_threshold_pp", 5.0)),
        poll_interval_sec=float(raw.get("poll_interval_sec", 120)),
        fee_kalshi_profit_pct=float(raw.get("fee_kalshi_profit_pct", 7.0)),
        verification_max_age_days=int(raw.get("verification_max_age_days", 14)),
        pairs=tuple(pairs),
        blockers=tuple(str(b) for b in raw.get("blockers") or ()),
        discovery=discovery,
    )
