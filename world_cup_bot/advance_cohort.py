"""K107 — advance-to-knockout cohort freshness vs cross_venue.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from world_cup_bot.cross_venue_config import CrossVenueConfig, load_cross_venue_config
from world_cup_bot.pm_discovery import PolymarketSnapshot, discover_polymarket_markets


@dataclass(frozen=True)
class AdvanceCohortRefresh:
    pm_advance_count: int
    firm_slug_count: int
    config_advance_slugs: int
    missing_from_config: tuple[str, ...]

    @property
    def needs_refresh(self) -> bool:
        return bool(self.missing_from_config)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pm_advance_count": self.pm_advance_count,
            "firm_slug_count": self.firm_slug_count,
            "config_advance_slugs": self.config_advance_slugs,
            "missing_from_config": list(self.missing_from_config),
            "needs_refresh": self.needs_refresh,
        }


def _config_advance_slugs(cfg: CrossVenueConfig) -> set[str]:
    return {
        str(p.polymarket_slug)
        for p in cfg.pairs
        if p.market_type == "advance_to_knockout" and p.polymarket_slug
    }


def firm_advance_markets(
    gamma_url: str,
) -> list[PolymarketSnapshot]:
    markets = discover_polymarket_markets(gamma_url)
    return [
        m
        for m in markets
        if m.market_type == "advance_to_knockout" and m.accepting_orders and m.slug
    ]


def scan_advance_cohort_refresh(
    *,
    gamma_url: str,
    cross_venue_config_path: Path,
) -> AdvanceCohortRefresh:
    pm_all = [
        m for m in discover_polymarket_markets(gamma_url) if m.market_type == "advance_to_knockout"
    ]
    firm = firm_advance_markets(gamma_url)
    cfg = load_cross_venue_config(cross_venue_config_path)
    configured = _config_advance_slugs(cfg)
    missing = tuple(sorted(m.slug for m in firm if m.slug and m.slug not in configured))
    return AdvanceCohortRefresh(
        pm_advance_count=len(pm_all),
        firm_slug_count=len(firm),
        config_advance_slugs=len(configured),
        missing_from_config=missing,
    )
