"""Gamma scanner — discover FIFA 2026 markets at runtime (multi-phase when router enabled)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from world_cup_bot import calendar_guard, team_names
from world_cup_bot.http_client import urlopen_get
from world_cup_bot.market_phases import MarketPhasesConfig
from world_cup_bot.operating_config import OperatingConfig, load_operating_config

_ADVANCE_QUESTION = re.compile(
    r"^Will (.+?) advance to the knockout stages at the 2026 FIFA World Cup\?$",
    re.IGNORECASE,
)
_SEARCH_QUERY = "world cup advance knockout"
DEFAULT_MIN_HOURS_BEFORE_KICKOFF = 10.0


@dataclass(frozen=True)
class PhaseScanTarget:
    phase_id: str
    pattern: re.Pattern[str]
    gamma_search: str
    priority: int


@dataclass(frozen=True)
class AdvanceMarket:
    team: str
    question: str
    slug: str
    condition_id: str
    yes_token_id: str
    no_token_id: str
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    mid: float | None
    rewards_min_shares: float | None
    rewards_max_spread: float | None
    liquidity: float | None
    volume: float | None
    accepting_orders: bool
    hours_to_kickoff: float | None
    must_cancel: bool
    bilateral_mode: bool
    min_hours_before_kickoff: float
    prefer_hours_before_kickoff: float
    market_phase_id: str = "group_advance"

    @property
    def kickoff_known(self) -> bool:
        return self.hours_to_kickoff is not None

    @property
    def rewards_params_ok(self) -> bool:
        return self.rewards_min_shares is not None and self.rewards_max_spread is not None

    @property
    def preferred_lp(self) -> bool:
        """Wiki: prefer quoting >24h before kickoff (soft gate for sorting/alerts)."""
        if not self.lp_eligible:
            return False
        return self.hours_to_kickoff >= self.prefer_hours_before_kickoff

    @property
    def lp_eligible(self) -> bool:
        """Fail closed: unknown kickoff or missing reward params → not eligible."""
        if not self.accepting_orders:
            return False
        if not self.kickoff_known:
            return False
        if not self.rewards_params_ok:
            return False
        if self.must_cancel:
            return False
        if self.hours_to_kickoff < self.min_hours_before_kickoff:
            return False
        return self.mid is not None


def _parse_json_field(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    return list(raw)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def parse_team_from_question(question: str) -> str | None:
    m = _ADVANCE_QUESTION.match(question.strip())
    if not m:
        return None
    return team_names.normalize_team(m.group(1))


def parse_team_with_pattern(question: str, pattern: re.Pattern[str]) -> str | None:
    m = pattern.match(question.strip())
    if not m:
        return None
    return team_names.normalize_team(m.group(1))


def build_scan_targets(
    config: MarketPhasesConfig,
    phase_ids: list[str],
) -> list[PhaseScanTarget]:
    targets: list[PhaseScanTarget] = []
    for pid in phase_ids:
        spec = config.phases.get(pid)
        if spec is None or not spec.title_regex:
            continue
        targets.append(
            PhaseScanTarget(
                phase_id=pid,
                pattern=re.compile(spec.title_regex, re.IGNORECASE),
                gamma_search=spec.gamma_search or _SEARCH_QUERY,
                priority=spec.scanner_priority,
            )
        )
    targets.sort(key=lambda t: (t.priority, t.phase_id))
    return targets


def parse_market(
    market: dict[str, Any],
    *,
    now: datetime | None = None,
    schedule: dict[str, list[datetime]] | None = None,
    min_hours_before_kickoff: float = DEFAULT_MIN_HOURS_BEFORE_KICKOFF,
    operating: OperatingConfig | None = None,
    team: str | None = None,
    market_phase_id: str = "group_advance",
) -> AdvanceMarket | None:
    question = market.get("question") or ""
    if team is None:
        team = parse_team_from_question(question)
    if not team:
        return None

    tokens = _parse_json_field(market.get("clobTokenIds"))
    if len(tokens) < 2:
        return None

    best_bid = _optional_float(market.get("bestBid"))
    best_ask = _optional_float(market.get("bestAsk"))
    spread = _optional_float(market.get("spread"))
    mid = None
    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2.0
    elif market.get("outcomePrices"):
        prices = _parse_json_field(market.get("outcomePrices"))
        if prices:
            mid = float(prices[0])

    now = now or datetime.now(UTC)
    hours = calendar_guard.hours_until_kickoff(team, now=now, schedule=schedule)
    must_cancel = calendar_guard.must_cancel_orders(
        team,
        min_hours_before_kickoff=min_hours_before_kickoff,
        now=now,
        schedule=schedule,
    )
    ops = operating or load_operating_config()
    bilateral = mid is not None and (mid >= ops.bilateral.high_mid or mid <= ops.bilateral.low_mid)

    return AdvanceMarket(
        team=team,
        question=question,
        slug=str(market.get("slug") or ""),
        condition_id=str(market.get("conditionId") or ""),
        yes_token_id=str(tokens[0]),
        no_token_id=str(tokens[1]),
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        mid=mid,
        rewards_min_shares=_optional_float(market.get("rewardsMinSize")),
        rewards_max_spread=_optional_float(market.get("rewardsMaxSpread")),
        liquidity=_optional_float(market.get("liquidity")),
        volume=_optional_float(market.get("volume")),
        accepting_orders=bool(market.get("acceptingOrders")),
        hours_to_kickoff=hours,
        must_cancel=must_cancel,
        bilateral_mode=bilateral,
        min_hours_before_kickoff=min_hours_before_kickoff,
        prefer_hours_before_kickoff=ops.calendar.prefer_hours_before_kickoff,
        market_phase_id=market_phase_id,
    )


def fetch_search_payload(
    gamma_url: str,
    query: str = _SEARCH_QUERY,
    *,
    opener: Any | None = None,
) -> dict[str, Any]:
    params = urllib.parse.urlencode({"q": query, "limit_per_type": "50"})
    url = f"{gamma_url}/public-search?{params}"
    if opener is not None:
        with opener(url, timeout=30) as resp:
            return json.loads(resp.read().decode())
    with urlopen_get(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def discover_markets(
    gamma_url: str = "https://gamma-api.polymarket.com",
    *,
    now: datetime | None = None,
    schedule: dict[str, list[datetime]] | None = None,
    min_hours_before_kickoff: float = DEFAULT_MIN_HOURS_BEFORE_KICKOFF,
    operating: OperatingConfig | None = None,
    opener: Any | None = None,
    phase_ids: list[str] | None = None,
    phases_config: MarketPhasesConfig | None = None,
) -> list[AdvanceMarket]:
    """Fetch markets from Gamma; filter by phase regex list when router provides phase_ids."""
    if not phase_ids or phases_config is None:
        return discover_advance_markets(
            gamma_url,
            now=now,
            schedule=schedule,
            min_hours_before_kickoff=min_hours_before_kickoff,
            operating=operating,
            opener=opener,
        )

    targets = build_scan_targets(phases_config, phase_ids)
    if not targets:
        return discover_advance_markets(
            gamma_url,
            now=now,
            schedule=schedule,
            min_hours_before_kickoff=min_hours_before_kickoff,
            operating=operating,
            opener=opener,
        )

    ops = operating or load_operating_config()
    sched = schedule if schedule is not None else calendar_guard.build_team_schedule()
    now = now or datetime.now(UTC)
    out: list[AdvanceMarket] = []
    seen_conditions: set[str] = set()
    payload_cache: dict[str, dict[str, Any]] = {}

    for target in targets:
        query = target.gamma_search
        if query not in payload_cache:
            try:
                payload_cache[query] = fetch_search_payload(gamma_url, query, opener=opener)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Gamma public-search failed for {query!r}: {exc}") from exc

        for event in payload_cache[query].get("events") or []:
            for market in event.get("markets") or []:
                question = str(market.get("question") or "")
                team = parse_team_with_pattern(question, target.pattern)
                if not team:
                    continue
                cid = str(market.get("conditionId") or "")
                if cid and cid in seen_conditions:
                    continue
                parsed = parse_market(
                    market,
                    now=now,
                    schedule=sched,
                    min_hours_before_kickoff=min_hours_before_kickoff,
                    operating=ops,
                    team=team,
                    market_phase_id=target.phase_id,
                )
                if parsed:
                    if cid:
                        seen_conditions.add(cid)
                    out.append(parsed)

    out.sort(key=lambda m: (m.market_phase_id, m.team.lower(), m.slug))
    return out


def discover_advance_markets(
    gamma_url: str = "https://gamma-api.polymarket.com",
    *,
    now: datetime | None = None,
    schedule: dict[str, list[datetime]] | None = None,
    min_hours_before_kickoff: float = DEFAULT_MIN_HOURS_BEFORE_KICKOFF,
    operating: OperatingConfig | None = None,
    opener: Any | None = None,
) -> list[AdvanceMarket]:
    """Fetch group-advance markets from Gamma public-search (v1 default)."""
    try:
        payload = fetch_search_payload(gamma_url, opener=opener)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Gamma public-search failed: {exc}") from exc

    ops = operating or load_operating_config()
    sched = schedule if schedule is not None else calendar_guard.build_team_schedule()
    now = now or datetime.now(UTC)
    out: list[AdvanceMarket] = []

    for event in payload.get("events") or []:
        for market in event.get("markets") or []:
            parsed = parse_market(
                market,
                now=now,
                schedule=sched,
                min_hours_before_kickoff=min_hours_before_kickoff,
                operating=ops,
            )
            if parsed:
                out.append(parsed)

    out.sort(key=lambda m: (m.team.lower(), m.slug))
    return out


def filter_lp_eligible(
    markets: list[AdvanceMarket],
    *,
    lp_only: bool = True,
    lp_phase_ids: set[str] | None = None,
) -> list[AdvanceMarket]:
    if not lp_only:
        return markets
    out = [m for m in markets if m.lp_eligible]
    if lp_phase_ids:
        out = [m for m in out if m.market_phase_id in lp_phase_ids]
    return out
