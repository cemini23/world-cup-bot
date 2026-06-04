"""Module 6 — PM vs Kalshi cross-venue gap scanner."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

from world_cup_bot import team_names
from world_cup_bot.cross_venue_config import (
    CrossVenueConfig,
    CrossVenuePair,
    load_cross_venue_config,
)
from world_cup_bot.kalshi_rest import KalshiMarketSnapshot, discover_wc_markets, fetch_market
from world_cup_bot.pm_discovery import (
    PolymarketSnapshot,
    discover_polymarket_markets,
    index_polymarket_by_slug,
    index_polymarket_markets,
    match_polymarket_for_pair,
)


@dataclass(frozen=True)
class CrossVenueScanRow:
    team: str
    market_type: str
    rules_hash: str
    gap_pp: float | None
    pm_mid: float | None
    kalshi_mid: float | None
    alert: bool
    pm_slug: str | None
    pm_question: str | None
    kalshi_ticker: str | None
    kalshi_title: str | None
    kalshi_volume_24h: float | None
    slug_changed: bool
    slug_change_detail: str | None
    blocked: bool
    block_reason: str | None
    notes: str | None
    source: str  # config | discovered

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveredPairProposal:
    team: str
    market_type: str
    rules_hash: str
    pm_slug: str
    pm_question: str
    pm_mid: float | None
    kalshi_ticker: str
    kalshi_title: str
    kalshi_mid: float | None
    gap_pp: float | None
    in_config: bool
    blocked: bool
    block_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def gap_pp(pm_mid: float | None, kalshi_mid: float | None) -> float | None:
    if pm_mid is None or kalshi_mid is None:
        return None
    return abs(pm_mid - kalshi_mid) * 100.0


def fee_adjusted_gap_note(gap: float | None, fee_pct: float) -> str | None:
    if gap is None:
        return None
    # Rough: Kalshi takes fee_pct of profit on winning leg — alert is raw gap, note net
    return f"raw {gap:.1f}pp; Kalshi ~{fee_pct:.0f}% on profit may erase sub-{fee_pct:.0f}pp gross"


def _slug_change(pair: CrossVenuePair, pm: PolymarketSnapshot | None) -> tuple[bool, str | None]:
    if pm is None or not pair.polymarket_slug:
        return False, None
    if pm.slug and pm.slug != pair.polymarket_slug:
        return True, f"config slug {pair.polymarket_slug!r} → live {pm.slug!r}"
    if pair.polymarket_condition_id and pm.condition_id != pair.polymarket_condition_id:
        return True, (
            f"condition_id changed {pair.polymarket_condition_id[:12]}… → {pm.condition_id[:12]}…"
        )
    return False, None


def _is_blocked_market_type(config: CrossVenueConfig, market_type: str) -> tuple[bool, str | None]:
    if market_type in config.discovery.blocked_market_types:
        return True, f"market_type {market_type!r} blocked until rules verified"
    return False, None


def _verification_stale(
    pair: CrossVenuePair,
    config: CrossVenueConfig,
) -> tuple[bool, str | None]:
    if not pair.rules_hash:
        return False, None
    if not pair.last_verified:
        return True, "last_verified missing — re-verify rules equivalence"
    try:
        verified = date.fromisoformat(str(pair.last_verified))
    except ValueError:
        return True, f"last_verified invalid date {pair.last_verified!r}"
    age_days = (datetime.now(UTC).date() - verified).days
    if age_days > config.verification_max_age_days:
        return True, (
            f"last_verified {pair.last_verified} stale "
            f"({age_days}d > {config.verification_max_age_days}d)"
        )
    return False, None


def scan_config_pair(
    pair: CrossVenuePair,
    config: CrossVenueConfig,
    *,
    pm: PolymarketSnapshot | None,
    kalshi: KalshiMarketSnapshot | None,
) -> CrossVenueScanRow:
    blocked, block_reason = _is_blocked_market_type(config, pair.market_type)
    if not pair.enabled:
        blocked = True
        block_reason = "pair disabled in config"
    stale, stale_reason = _verification_stale(pair, config)
    if stale:
        blocked = True
        block_reason = stale_reason or block_reason

    slug_changed, slug_detail = _slug_change(pair, pm)
    g = gap_pp(pm.mid if pm else None, kalshi.mid if kalshi else None)
    alert = (
        not blocked and g is not None and g >= config.alert_threshold_pp and pair.rules_hash != ""
    )

    return CrossVenueScanRow(
        team=pair.team,
        market_type=pair.market_type,
        rules_hash=pair.rules_hash,
        gap_pp=g,
        pm_mid=pm.mid if pm else None,
        kalshi_mid=kalshi.mid if kalshi else None,
        alert=alert,
        pm_slug=pm.slug if pm else None,
        pm_question=pm.question if pm else None,
        kalshi_ticker=kalshi.ticker if kalshi else pair.kalshi_market_ticker or None,
        kalshi_title=kalshi.title if kalshi else None,
        kalshi_volume_24h=kalshi.volume_24h if kalshi else None,
        slug_changed=slug_changed,
        slug_change_detail=slug_detail,
        blocked=blocked,
        block_reason=block_reason,
        notes=pair.notes,
        source="config",
    )


def scan_config_pairs(
    config: CrossVenueConfig,
    *,
    pm_markets: list[PolymarketSnapshot],
    kalshi_by_ticker: dict[str, KalshiMarketSnapshot],
    team_filter: str | None = None,
    kalshi_fetcher: Any = fetch_market,
    kalshi_base_url: str | None = None,
    opener: Any | None = None,
) -> list[CrossVenueScanRow]:
    catalog = index_polymarket_markets(pm_markets)
    slug_index = index_polymarket_by_slug(pm_markets)
    rows: list[CrossVenueScanRow] = []

    for pair in config.pairs:
        if team_filter and not team_names.teams_match(pair.team, team_filter):
            continue

        pm = match_polymarket_for_pair(
            team=pair.team,
            market_type=pair.market_type,
            hint=pair.polymarket_hint,
            catalog=catalog,
            markets=pm_markets,
            polymarket_slug=pair.polymarket_slug,
            slug_index=slug_index,
        )

        kalshi: KalshiMarketSnapshot | None = None
        ticker = pair.kalshi_market_ticker
        if ticker and ticker in kalshi_by_ticker:
            kalshi = kalshi_by_ticker[ticker]
        elif ticker:
            try:
                kwargs: dict[str, Any] = {"opener": opener}
                if kalshi_base_url:
                    kwargs["base_url"] = kalshi_base_url
                kalshi = kalshi_fetcher(ticker, **kwargs)
            except RuntimeError:
                kalshi = None

        rows.append(scan_config_pair(pair, config, pm=pm, kalshi=kalshi))

    return rows


def discover_candidate_pairs(
    config: CrossVenueConfig,
    *,
    pm_markets: list[PolymarketSnapshot],
    kalshi_markets: list[KalshiMarketSnapshot],
) -> list[DiscoveredPairProposal]:
    """Auto-pair PM + Kalshi by team + market_type for markets not yet in config."""
    config_keys = {p.pair_key for p in config.pairs}
    kalshi_idx: dict[str, KalshiMarketSnapshot] = {}
    for k in kalshi_markets:
        if k.team:
            kalshi_idx[f"{k.market_type}:{k.team}"] = k

    proposals: list[DiscoveredPairProposal] = []
    for pm in pm_markets:
        key = pm.pair_key
        kalshi = kalshi_idx.get(key)
        if kalshi is None:
            continue

        rules = config.discovery.rules_hash_by_market_type.get(pm.market_type, "")
        blocked, block_reason = _is_blocked_market_type(config, pm.market_type)
        g = gap_pp(pm.mid, kalshi.mid)

        proposals.append(
            DiscoveredPairProposal(
                team=pm.team,
                market_type=pm.market_type,
                rules_hash=rules,
                pm_slug=pm.slug,
                pm_question=pm.question,
                pm_mid=pm.mid,
                kalshi_ticker=kalshi.ticker,
                kalshi_title=kalshi.title,
                kalshi_mid=kalshi.mid,
                gap_pp=g,
                in_config=key in config_keys,
                blocked=blocked,
                block_reason=block_reason,
            )
        )

    proposals.sort(key=lambda p: (-(p.gap_pp or 0), p.team))
    return proposals


@dataclass(frozen=True)
class CrossVenueScanResult:
    scanned_at: str
    config_version: int
    alert_threshold_pp: float
    blockers: tuple[str, ...]
    rows: tuple[CrossVenueScanRow, ...]
    discoveries: tuple[DiscoveredPairProposal, ...]
    pm_market_count: int
    kalshi_market_count: int

    @property
    def alerts(self) -> list[CrossVenueScanRow]:
        return [r for r in self.rows if r.alert]

    @property
    def slug_warnings(self) -> list[CrossVenueScanRow]:
        return [r for r in self.rows if r.slug_changed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_at": self.scanned_at,
            "config_version": self.config_version,
            "alert_threshold_pp": self.alert_threshold_pp,
            "blockers": list(self.blockers),
            "pm_market_count": self.pm_market_count,
            "kalshi_market_count": self.kalshi_market_count,
            "alerts": [r.to_dict() for r in self.alerts],
            "slug_warnings": [r.to_dict() for r in self.slug_warnings],
            "rows": [r.to_dict() for r in self.rows],
            "discoveries": [d.to_dict() for d in self.discoveries],
        }


def run_scan(
    config: CrossVenueConfig | None = None,
    *,
    gamma_url: str = "https://gamma-api.polymarket.com",
    kalshi_base_url: str = "https://api.elections.kalshi.com/trade-api/v2",
    team_filter: str | None = None,
    include_discoveries: bool = True,
    opener: Any | None = None,
    pm_fetcher: Any = discover_polymarket_markets,
    kalshi_discoverer: Any = discover_wc_markets,
) -> CrossVenueScanResult:
    cfg = config or load_cross_venue_config()

    pm_markets = pm_fetcher(
        gamma_url,
        search_queries=cfg.discovery.polymarket_search_queries,
        opener=opener,
    )
    kalshi_markets = kalshi_discoverer(
        ticker_prefixes=cfg.discovery.kalshi_ticker_prefixes,
        base_url=kalshi_base_url,
        extra_event_tickers=tuple(
            p.kalshi_event_ticker for p in cfg.pairs if p.kalshi_event_ticker
        ),
        opener=opener,
    )
    kalshi_by_ticker = {m.ticker: m for m in kalshi_markets}

    rows = scan_config_pairs(
        cfg,
        pm_markets=pm_markets,
        kalshi_by_ticker=kalshi_by_ticker,
        team_filter=team_filter,
        kalshi_base_url=kalshi_base_url,
        opener=opener,
    )

    discoveries: tuple[DiscoveredPairProposal, ...] = ()
    if include_discoveries:
        discoveries = tuple(
            discover_candidate_pairs(cfg, pm_markets=pm_markets, kalshi_markets=kalshi_markets)
        )

    return CrossVenueScanResult(
        scanned_at=datetime.now(UTC).isoformat(),
        config_version=cfg.version,
        alert_threshold_pp=cfg.alert_threshold_pp,
        blockers=cfg.blockers,
        rows=tuple(rows),
        discoveries=discoveries,
        pm_market_count=len(pm_markets),
        kalshi_market_count=len(kalshi_markets),
    )
