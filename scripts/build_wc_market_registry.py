#!/usr/bin/env python3
"""Build config/wc_market_registry.json from fixtures + cross_venue.yaml."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from world_cup_bot.calendar_guard import _is_scheduled_team, load_fixtures
from world_cup_bot.team_names import normalize_team


def _group_stage_teams() -> list[str]:
    fixtures = load_fixtures(ROOT / "data" / "worldcup2026-fixtures.json")
    teams: set[str] = set()
    for match in fixtures.get("matches") or []:
        if not str(match.get("round") or "").startswith("Matchday"):
            continue
        for raw in (match.get("team1"), match.get("team2")):
            if _is_scheduled_team(raw):
                teams.add(normalize_team(str(raw)))
    return sorted(teams)


def _kalshi_team_code(team: str) -> str:
    """Best-effort Kalshi suffix (verified pairs override in cross_venue.yaml)."""
    aliases = {
        "USA": "USA",
        "South Korea": "KOR",
        "Ivory Coast": "CIV",
        "Bosnia & Herzegovina": "BIH",
        "DR Congo": "COD",
        "Curaçao": "CUW",
        "Czech Republic": "CZE",
        "Turkey": "TUR",
        "England": "ENG",
        "Netherlands": "NED",
        "Germany": "GER",
        "France": "FRA",
        "Spain": "SPA",
        "Portugal": "POR",
        "Brazil": "BRA",
        "Argentina": "ARG",
        "Mexico": "MEX",
        "Canada": "CAN",
        "Japan": "JPN",
        "Australia": "AUS",
        "Switzerland": "SUI",
        "Belgium": "BEL",
        "Croatia": "CRO",
        "Scotland": "SCO",
        "Norway": "NOR",
        "Denmark": "DEN",
        "Poland": "POL",
        "Ukraine": "UKR",
        "Ecuador": "ECU",
        "Colombia": "COL",
        "Uruguay": "URU",
        "Paraguay": "PAR",
        "Chile": "CHI",
        "Peru": "PER",
        "Morocco": "MAR",
        "Senegal": "SEN",
        "Nigeria": "NGA",
        "Ghana": "GHA",
        "Cameroon": "CMR",
        "Algeria": "ALG",
        "Tunisia": "TUN",
        "Egypt": "EGY",
        "Iran": "IRN",
        "Qatar": "QAT",
        "Saudi Arabia": "SAU",
        "Jordan": "JOR",
        "New Zealand": "NZL",
        "Panama": "PAN",
        "Costa Rica": "CRC",
        "Honduras": "HON",
        "Jamaica": "JAM",
        "Wales": "WAL",
        "Serbia": "SRB",
        "Austria": "AUT",
        "Hungary": "HUN",
        "Romania": "ROU",
        "Slovakia": "SVK",
        "Albania": "ALB",
        "Georgia": "GEO",
        "Cape Verde": "CPV",
    }
    if team in aliases:
        return aliases[team]
    parts = team.upper().replace("&", "").split()
    if len(parts) >= 2:
        return (parts[0][:1] + parts[-1][:2])[:3]
    return team.upper()[:3]


def _verified_qual_pairs(cv_path: Path) -> dict[str, dict]:
    raw = yaml.safe_load(cv_path.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    for row in raw.get("pairs") or []:
        if row.get("market_type") != "group_qualify":
            continue
        team = str(row.get("team") or "")
        if team:
            out[team] = row
    return out


def build() -> dict:
    teams = _group_stage_teams()
    verified = _verified_qual_pairs(ROOT / "config" / "cross_venue.yaml")
    pm_events = []
    for team in teams:
        verified_row = verified.get(team)
        ticker_hint = None
        if verified_row:
            ticker_hint = str(verified_row.get("kalshi_market_ticker") or "")
        else:
            code = _kalshi_team_code(team)
            ticker_hint = f"KXWCGROUPQUAL-26*-{code}"
        pm_events.append(
            {
                "team": team,
                "slug_hint": f"advance knockout {team.lower()}",
                "resolution_class": "group_advance_r32",
                "rewards_lp_eligible": True,
                "kalshi_ticker_hint": ticker_hint,
            }
        )
    cross_pairs = [
        {
            "rules_hash": "MATCH_01",
            "pairable": True,
            "pm_slug_hint": "world-cup-winner",
            "kalshi_series": "KXMENWORLDCUP",
        },
        {
            "rules_hash": "MATCH_02",
            "pairable": True,
            "pm_slug_hint": "world-cup-group-",
            "kalshi_series": "KXWCGROUPWIN-26",
        },
        {
            "rules_hash": "MATCH_03",
            "pairable": True,
            "pm_slug_hint": "team-to-advance",
            "kalshi_series": "KXWCGROUPQUAL-26",
        },
        {
            "rules_hash": "MATCH_04",
            "pairable": True,
            "pm_slug_hint": "reach-quarterfinals",
            "kalshi_series": "KXWCROUND-26QUAR",
        },
    ]
    for team, row in sorted(verified.items()):
        cross_pairs.append(
            {
                "rules_hash": str(row.get("rules_hash") or "group_qualify_v1"),
                "pairable": bool(row.get("enabled", True)),
                "team": team,
                "pm_slug_hint": str(row.get("polymarket_hint") or "")[:80],
                "kalshi_series": str(row.get("kalshi_event_ticker") or ""),
                "kalshi_market_ticker": str(row.get("kalshi_market_ticker") or ""),
            }
        )
    return {
        "schema": "wc_market_registry_v1",
        "pulled_at_utc": datetime.now(UTC).strftime("%Y-%m-%d"),
        "polymarket_events": pm_events,
        "kalshi_series": [
            "KXMENWORLDCUP",
            "KXWCGROUPWIN-26",
            "KXWCGROUPQUAL-26",
            "KXWCROUND-26QUAR",
            "KXWCROUND-26RO16",
            "KXWCROUND-26SEMI",
            "KXWCROUND-26FINAL",
            "KXWCGAME",
        ],
        "cross_venue_pairs": cross_pairs,
        "lp_routing": {
            "eligible": [
                "group_advance_r32",
                "reach_r16",
                "reach_qf",
                "reach_sf",
                "reach_final",
                "outright_winner",
            ],
            "excluded": ["group_winner", "stage_of_elimination", "match_winner"],
        },
    }


def main() -> None:
    out_path = ROOT / "config" / "wc_market_registry.json"
    payload = build()
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    n = sum(1 for e in payload["polymarket_events"] if e["resolution_class"] == "group_advance_r32")
    print(f"Wrote {out_path} ({n} group_advance_r32 entries)")


if __name__ == "__main__":
    main()
