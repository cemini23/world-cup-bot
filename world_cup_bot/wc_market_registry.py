"""K109 market registry — LP routing + inventory validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from world_cup_bot.paths import resolve_project_path

_DEFAULT_REGISTRY = Path(__file__).resolve().parent.parent / "config" / "wc_market_registry.json"

# Map scanner phase_id → registry resolution_class (K109 catalog).
PHASE_TO_RESOLUTION_CLASS: dict[str, str] = {
    "group_advance": "group_advance_r32",
    "reach_round_of_16": "reach_r16",
    "reach_quarterfinal": "reach_qf",
    "reach_semifinal": "reach_sf",
    "reach_final": "reach_final",
    "wc_winner": "outright_winner",
    "knockout_match_90min": "match_winner",
    "knockout_match_advance": "match_winner",
}


@dataclass(frozen=True)
class RegistryEvent:
    team: str | None
    slug_hint: str | None
    resolution_class: str
    rewards_lp_eligible: bool
    kalshi_ticker_hint: str | None = None


@dataclass(frozen=True)
class WcMarketRegistry:
    schema: str
    pulled_at_utc: str
    polymarket_events: tuple[RegistryEvent, ...]
    kalshi_series: tuple[str, ...]
    cross_venue_pairs: tuple[dict[str, Any], ...]
    lp_eligible_resolution_classes: frozenset[str]
    lp_excluded_resolution_classes: frozenset[str]

    def count_group_advance_r32(self) -> int:
        return sum(1 for e in self.polymarket_events if e.resolution_class == "group_advance_r32")

    def count_kalshi_groupqual_hints(self) -> int:
        return sum(
            1
            for e in self.polymarket_events
            if e.resolution_class == "group_advance_r32"
            and e.kalshi_ticker_hint
            and "GROUPQUAL" in e.kalshi_ticker_hint.upper()
        )

    def resolution_class_for_phase(self, phase_id: str | None) -> str | None:
        if not phase_id:
            return None
        return PHASE_TO_RESOLUTION_CLASS.get(phase_id)

    def lp_allowed_for_phase(self, phase_id: str | None) -> bool:
        rc = self.resolution_class_for_phase(phase_id)
        if rc is None:
            return True
        if rc in self.lp_excluded_resolution_classes:
            return False
        if self.lp_eligible_resolution_classes:
            return rc in self.lp_eligible_resolution_classes
        return True


def load_wc_market_registry(path: Path | None = None) -> WcMarketRegistry:
    p = path or resolve_project_path("config/wc_market_registry.json")
    if not p.is_file():
        p = _DEFAULT_REGISTRY
    raw = json.loads(p.read_text(encoding="utf-8"))
    events: list[RegistryEvent] = []
    for row in raw.get("polymarket_events") or []:
        if not isinstance(row, dict):
            continue
        events.append(
            RegistryEvent(
                team=row.get("team"),
                slug_hint=row.get("slug_hint"),
                resolution_class=str(row.get("resolution_class") or ""),
                rewards_lp_eligible=bool(row.get("rewards_lp_eligible", False)),
                kalshi_ticker_hint=row.get("kalshi_ticker_hint"),
            )
        )
    lp_block = raw.get("lp_routing") or {}
    eligible_raw = lp_block.get("eligible") or raw.get("lp_eligible_resolution_classes") or ()
    eligible = frozenset(str(x) for x in eligible_raw)
    excluded_raw = lp_block.get("excluded") or raw.get("lp_excluded_resolution_classes") or ()
    excluded = frozenset(str(x) for x in excluded_raw)
    return WcMarketRegistry(
        schema=str(raw.get("schema") or "wc_market_registry_v1"),
        pulled_at_utc=str(raw.get("pulled_at_utc") or ""),
        polymarket_events=tuple(events),
        kalshi_series=tuple(str(x) for x in (raw.get("kalshi_series") or ())),
        cross_venue_pairs=tuple(raw.get("cross_venue_pairs") or ()),
        lp_eligible_resolution_classes=eligible,
        lp_excluded_resolution_classes=excluded,
    )


@lru_cache(maxsize=1)
def get_wc_market_registry() -> WcMarketRegistry:
    return load_wc_market_registry()
