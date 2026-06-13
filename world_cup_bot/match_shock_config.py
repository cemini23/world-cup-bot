"""Load Module 8 match-shock config from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_SHOCK_MATCH = Path(__file__).resolve().parent.parent / "config" / "shock_match.yaml"


@dataclass(frozen=True)
class DetectionConfig:
    window_ms: int
    min_drop_pct: float
    min_drop_abs: float
    cooldown_ms: int


@dataclass(frozen=True)
class FavoritismThresholds:
    heavy_fav_min: float
    moderate_fav_min: float
    slight_fav_min: float
    balanced_min: float


@dataclass(frozen=True)
class ClassifierConfig:
    deep_slugs: tuple[str, ...]
    thin_slugs: tuple[str, ...]
    favoritism: FavoritismThresholds
    top_heavy_ratio: float
    balanced_ratio: float
    early_max_min: int
    mid_max_min: int
    late_max_min: int
    blowout_diff: int


@dataclass(frozen=True)
class DistributionConfig:
    min_samples_per_bucket: int
    default_percentiles_cents: dict[int, float]
    percentile_keys: tuple[int, ...]


@dataclass(frozen=True)
class LadderConfig:
    capital_usd: float
    order_ttl_ms: int
    recovery_target_cents: float
    weights: dict[int, float]


@dataclass(frozen=True)
class BacktestFilterConfig:
    allowed_favoritism: frozenset[str]
    allowed_league_tiers: frozenset[str]
    min_recovery_rate: float


@dataclass(frozen=True)
class MarketScopeConfig:
    slug_patterns: tuple[str, ...]
    blocked_slug_patterns: tuple[str, ...]


@dataclass(frozen=True)
class MatchShockConfig:
    version: int
    enabled: bool
    detection: DetectionConfig
    classifiers: ClassifierConfig
    distribution: DistributionConfig
    ladder: LadderConfig
    backtest: BacktestFilterConfig
    markets: MarketScopeConfig
    paper_ledger_suffix: str
    paper_dedup_interval_ms: int
    live_tape_window_ms: int
    live_max_notional_per_shock_usd: float
    live_max_open_shocks: int
    live_max_daily_notional_usd: float


def load_match_shock_config(path: Path | None = None) -> MatchShockConfig:
    p = path or DEFAULT_SHOCK_MATCH
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    det = raw.get("detection") or {}
    clf = raw.get("classifiers") or {}
    fav = clf.get("favoritism") or {}
    dist = raw.get("distribution") or {}
    lad = raw.get("ladder") or {}
    bt = raw.get("backtest") or {}
    mkt = raw.get("markets") or {}
    paper = raw.get("paper") or {}
    live = raw.get("live") or {}

    default_pcts_raw = dist.get("default_percentiles_cents") or {}
    default_pcts = {int(k): float(v) for k, v in default_pcts_raw.items()}

    weights_raw = lad.get("weights") or {}
    weights = {int(k): float(v) for k, v in weights_raw.items()}

    pct_keys = tuple(int(x) for x in (dist.get("percentile_keys") or [50, 75, 90, 95]))

    return MatchShockConfig(
        version=int(raw.get("version", 1)),
        enabled=bool(raw.get("enabled", False)),
        detection=DetectionConfig(
            window_ms=int(det.get("window_ms", 120_000)),
            min_drop_pct=float(det.get("min_drop_pct", 0.15)),
            min_drop_abs=float(det.get("min_drop_abs", 0.08)),
            cooldown_ms=int(det.get("cooldown_ms", 180_000)),
        ),
        classifiers=ClassifierConfig(
            deep_slugs=tuple(str(x) for x in (clf.get("league") or {}).get("deep_slugs") or ()),
            thin_slugs=tuple(str(x) for x in (clf.get("league") or {}).get("thin_slugs") or ()),
            favoritism=FavoritismThresholds(
                heavy_fav_min=float(fav.get("heavy_fav_min", 0.85)),
                moderate_fav_min=float(fav.get("moderate_fav_min", 0.75)),
                slight_fav_min=float(fav.get("slight_fav_min", 0.60)),
                balanced_min=float(fav.get("balanced_min", 0.45)),
            ),
            top_heavy_ratio=float((clf.get("book_depth") or {}).get("top_heavy_ratio", 0.70)),
            balanced_ratio=float((clf.get("book_depth") or {}).get("balanced_ratio", 0.50)),
            early_max_min=int((clf.get("match_time") or {}).get("early_max_min", 15)),
            mid_max_min=int((clf.get("match_time") or {}).get("mid_max_min", 60)),
            late_max_min=int((clf.get("match_time") or {}).get("late_max_min", 80)),
            blowout_diff=int((clf.get("goal_state") or {}).get("blowout_diff", 3)),
        ),
        distribution=DistributionConfig(
            min_samples_per_bucket=int(dist.get("min_samples_per_bucket", 5)),
            default_percentiles_cents=default_pcts,
            percentile_keys=pct_keys,
        ),
        ladder=LadderConfig(
            capital_usd=float(lad.get("capital_usd", 50.0)),
            order_ttl_ms=int(lad.get("order_ttl_ms", 60_000)),
            recovery_target_cents=float(lad.get("recovery_target_cents", 4.0)),
            weights=weights,
        ),
        backtest=BacktestFilterConfig(
            allowed_favoritism=frozenset(str(x) for x in (bt.get("allowed_favoritism") or ())),
            allowed_league_tiers=frozenset(str(x) for x in (bt.get("allowed_league_tiers") or ())),
            min_recovery_rate=float(bt.get("min_recovery_rate", 0.55)),
        ),
        markets=MarketScopeConfig(
            slug_patterns=tuple(str(x) for x in (mkt.get("slug_patterns") or ())),
            blocked_slug_patterns=tuple(str(x) for x in (mkt.get("blocked_slug_patterns") or ())),
        ),
        paper_ledger_suffix=str(paper.get("ledger_suffix", "match_shock_paper.jsonl")),
        paper_dedup_interval_ms=int(paper.get("dedup_interval_ms", 300_000)),
        live_tape_window_ms=int(live.get("tape_window_ms", 900_000)),
        live_max_notional_per_shock_usd=float(live.get("max_notional_per_shock_usd", 50)),
        live_max_open_shocks=int(live.get("max_open_shocks", 2)),
        live_max_daily_notional_usd=float(live.get("max_daily_notional_usd", 500)),
    )
