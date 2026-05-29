"""Normalize team names between fixture data and Polymarket slugs."""

from __future__ import annotations

ALIASES: dict[str, str] = {
    "united states": "USA",
    "usa": "USA",
    "u.s.a.": "USA",
    "u.s.": "USA",
    "south korea": "South Korea",
    "korea republic": "South Korea",
    "korea, republic of": "South Korea",
    "ivory coast": "Ivory Coast",
    "cote d'ivoire": "Ivory Coast",
    "côte d'ivoire": "Ivory Coast",
    "bosnia and herzegovina": "Bosnia & Herzegovina",
    "bosnia": "Bosnia & Herzegovina",
    "dr congo": "DR Congo",
    "congo dr": "DR Congo",
    "democratic republic of the congo": "DR Congo",
    "curacao": "Curaçao",
    "czechia": "Czech Republic",
    "turkiye": "Turkey",
    "türkiye": "Turkey",
}

_FIXTURE_CANONICAL: set[str] = set()


def normalize_team(name: str) -> str:
    key = name.strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    for fixture_name in _FIXTURE_CANONICAL:
        if fixture_name.lower() == key:
            return fixture_name
    return name.strip()


def teams_match(fixture_name: str, query: str) -> bool:
    return normalize_team(fixture_name) == normalize_team(query)
