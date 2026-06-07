"""Group-stage travel burden — slight notional multiplier from base camp vs match miles."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from world_cup_bot import team_names
from world_cup_bot.calendar_guard import load_fixtures
from world_cup_bot.paths import resolve_project_path

DEFAULT_CONFIG = resolve_project_path("config/travel_burden.yaml")
DEFAULT_BASE_CAMPS = resolve_project_path("data/wc2026-base-camps.yaml")
DEFAULT_HOST_CITIES = resolve_project_path("data/wc2026-host-cities.yaml")

EARTH_RADIUS_MI = 3958.8


@dataclass(frozen=True)
class TravelBurdenConfig:
    enabled: bool
    max_notional_penalty_pct: float
    miles_no_penalty_below: float
    miles_full_penalty_at: float


@dataclass(frozen=True)
class TravelBurdenState:
    team: str
    max_one_way_miles: float | None
    notional_multiplier: float
    base_hub: str | None = None
    farthest_ground: str | None = None


def load_travel_burden_config(path: Path | str | None = None) -> TravelBurdenConfig:
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    raw = yaml.safe_load(cfg_path.read_text()) or {}
    return TravelBurdenConfig(
        enabled=bool(raw.get("enabled", True)),
        max_notional_penalty_pct=float(raw.get("max_notional_penalty_pct", 0.06)),
        miles_no_penalty_below=float(raw.get("miles_no_penalty_below", 300)),
        miles_full_penalty_at=float(raw.get("miles_full_penalty_at", 2000)),
    )


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _load_base_camps(path: str) -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    out: dict[str, dict[str, Any]] = {}
    for team, spec in (raw.get("teams") or {}).items():
        canon = team_names.normalize_team(team)
        out[canon] = spec
    return out


@lru_cache(maxsize=1)
def _load_host_cities(path: str) -> dict[str, dict[str, float]]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return dict(raw.get("host_cities") or {})


def _group_match_grounds(team: str, fixtures: dict[str, Any]) -> list[str]:
    canon = team_names.normalize_team(team)
    grounds: list[str] = []
    for row in fixtures.get("matches") or []:
        t1 = team_names.normalize_team(str(row.get("team1") or ""))
        t2 = team_names.normalize_team(str(row.get("team2") or ""))
        if canon not in {t1, t2}:
            continue
        ground = row.get("ground")
        if ground:
            grounds.append(str(ground))
    return grounds


def max_one_way_travel_miles(
    team: str,
    *,
    fixtures: dict[str, Any] | None = None,
    base_camps_path: Path | str | None = None,
    host_cities_path: Path | str | None = None,
) -> tuple[float | None, str | None, str | None]:
    """Return (miles, base_hub, farthest_ground) for team's group stage."""
    camps = _load_base_camps(str(base_camps_path or DEFAULT_BASE_CAMPS))
    hosts = _load_host_cities(str(host_cities_path or DEFAULT_HOST_CITIES))
    canon = team_names.normalize_team(team)
    camp = camps.get(canon)
    if not camp:
        return None, None, None

    data = fixtures if fixtures is not None else load_fixtures()
    grounds = _group_match_grounds(canon, data)
    if not grounds:
        return None, camp.get("hub"), None

    base_lat = float(camp["lat"])
    base_lon = float(camp["lon"])
    max_miles = 0.0
    farthest = None
    for ground in grounds:
        city = hosts.get(ground)
        if not city:
            continue
        miles = _haversine_miles(base_lat, base_lon, float(city["lat"]), float(city["lon"]))
        if miles > max_miles:
            max_miles = miles
            farthest = ground
    if farthest is None:
        return None, camp.get("hub"), None
    return round(max_miles, 1), camp.get("hub"), farthest


def notional_multiplier_from_miles(miles: float, cfg: TravelBurdenConfig) -> float:
    if miles <= cfg.miles_no_penalty_below:
        return 1.0
    span = cfg.miles_full_penalty_at - cfg.miles_no_penalty_below
    if span <= 0:
        return 1.0 - cfg.max_notional_penalty_pct
    ratio = min(1.0, max(0.0, (miles - cfg.miles_no_penalty_below) / span))
    return round(1.0 - cfg.max_notional_penalty_pct * ratio, 4)


def travel_burden_state(
    team: str,
    cfg: TravelBurdenConfig | None = None,
    *,
    fixtures: dict[str, Any] | None = None,
) -> TravelBurdenState:
    cfg = cfg or load_travel_burden_config()
    canon = team_names.normalize_team(team)
    if not cfg.enabled:
        return TravelBurdenState(canon, None, 1.0)

    miles, hub, farthest = max_one_way_travel_miles(canon, fixtures=fixtures)
    if miles is None:
        return TravelBurdenState(canon, None, 1.0, base_hub=hub, farthest_ground=farthest)

    mult = notional_multiplier_from_miles(miles, cfg)
    return TravelBurdenState(
        team=canon,
        max_one_way_miles=miles,
        notional_multiplier=mult,
        base_hub=hub,
        farthest_ground=farthest,
    )


def travel_notional_multiplier(
    team: str,
    cfg: TravelBurdenConfig | None = None,
) -> float:
    return travel_burden_state(team, cfg).notional_multiplier
