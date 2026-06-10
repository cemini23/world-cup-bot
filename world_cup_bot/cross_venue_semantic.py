"""K109 semantic blocklist — suppress invalid PM↔Kalshi pairings before gap math."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from world_cup_bot.paths import resolve_project_path

_DEFAULT_RULES = Path(__file__).resolve().parent.parent / "config" / "wc_semantic_rules.yaml"


@dataclass(frozen=True)
class SemanticBlockRule:
    id: str
    reason: str
    pm_slug_patterns: tuple[str, ...]
    kalshi_ticker_patterns: tuple[str, ...]
    pm_market_types: frozenset[str]


@dataclass(frozen=True)
class SemanticRulesConfig:
    schema: str
    blocklist: tuple[SemanticBlockRule, ...]
    kalshi_macro_unhedged_prefixes: tuple[str, ...]

    def check(
        self,
        *,
        pm_slug: str | None,
        kalshi_ticker: str | None,
        pm_market_type: str | None,
    ) -> tuple[str, str] | None:
        slug = (pm_slug or "").lower()
        ticker = (kalshi_ticker or "").upper()
        mtype = (pm_market_type or "").lower()
        for rule in self.blocklist:
            if rule.pm_market_types and mtype and mtype not in rule.pm_market_types:
                continue
            kal_match = not rule.kalshi_ticker_patterns
            if rule.kalshi_ticker_patterns:
                kal_match = any(_pattern_match(ticker, pat) for pat in rule.kalshi_ticker_patterns)
            slug_match = not rule.pm_slug_patterns
            if rule.pm_slug_patterns:
                slug_match = any(_pattern_match(slug, pat.lower()) for pat in rule.pm_slug_patterns)
            if kal_match and slug_match and (rule.pm_slug_patterns or rule.kalshi_ticker_patterns):
                return rule.id, rule.reason
        return None

    def is_macro_unhedged(self, kalshi_ticker: str) -> bool:
        t = kalshi_ticker.upper()
        return any(t.startswith(p) for p in self.kalshi_macro_unhedged_prefixes)


def _pattern_match(value: str, pattern: str) -> bool:
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatch(value, pattern)
    return pattern in value


def load_semantic_rules(path: Path | None = None) -> SemanticRulesConfig:
    p = path or resolve_project_path("config/wc_semantic_rules.yaml")
    if not p.is_file():
        p = _DEFAULT_RULES
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    blocks: list[SemanticBlockRule] = []
    for row in raw.get("semantic_blocklist") or []:
        blocks.append(
            SemanticBlockRule(
                id=str(row.get("id") or ""),
                reason=str(row.get("reason") or ""),
                pm_slug_patterns=tuple(row.get("pm_slug_patterns") or ()),
                kalshi_ticker_patterns=tuple(row.get("kalshi_ticker_patterns") or ()),
                pm_market_types=frozenset(str(x) for x in (row.get("pm_market_types") or ())),
            )
        )
    macros = tuple(str(x) for x in (raw.get("kalshi_macro_unhedged_prefixes") or ()))
    return SemanticRulesConfig(
        schema=str(raw.get("schema") or "wc_semantic_rules_v1"),
        blocklist=tuple(blocks),
        kalshi_macro_unhedged_prefixes=macros,
    )


def suppression_event(
    *,
    block_id: str,
    reason: str,
    rules_hash: str | None,
    pm_slug: str | None,
    kalshi_ticker: str | None,
    team: str | None = None,
    market_type: str | None = None,
) -> dict[str, Any]:
    return {
        "event": "cross_venue_suppressed",
        "block_id": block_id,
        "reason": reason,
        "rules_hash": rules_hash or "",
        "team": team,
        "market_type": market_type,
        "pm_slug": pm_slug,
        "kalshi_ticker": kalshi_ticker,
    }
