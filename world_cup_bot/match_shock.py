"""Module 8 — in-play match-market shock detection, classification, and ladder planning.

Paper-first v2 strategy orthogonal to advance-LP quoter (wc_advance_lp_v4).
Spec: docs/MATCH_SHOCK_V1.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.match_shock_config import ClassifierConfig, LadderConfig, MatchShockConfig

MATCH_SHOCK_SPEC = StrategyVersionSpec(
    strategy_key="pm_wc_match_shock",
    version_id="wc_match_shock_v1",
    deployed_at=datetime(2026, 6, 2, tzinfo=UTC),
    note="In-play match-market shock recovery — paper-first; isolated from advance LP",
    legacy_version_ids=frozenset(),
)

EVENT_SHOCK_DETECTED = "match_shock_detected"
EVENT_LADDER_PLANNED = "match_shock_ladder_planned"
EVENT_PAPER_FILL = "match_shock_paper_fill"


@dataclass(frozen=True)
class PriceTick:
    ts_ms: int
    price: float


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class ShockContext:
    slug: str
    pre_price: float
    bids: tuple[BookLevel, ...]
    elapsed_ms: int
    goal_diff: int


@dataclass(frozen=True)
class ShockDetection:
    shock: bool
    peak: float | None = None
    floor: float | None = None
    depth: float | None = None
    pre_price: float | None = None


@dataclass(frozen=True)
class LadderOrder:
    percentile: int
    limit_price: float
    size_usd: float
    weight: float


@dataclass(frozen=True)
class LadderPlan:
    bucket_key: str
    pre_price: float
    percentiles_cents: dict[int, float]
    orders: tuple[LadderOrder, ...]
    recovery_target_price: float


def detect_shock(
    window_ticks: tuple[PriceTick, ...],
    *,
    min_drop_pct: float,
    min_drop_abs: float,
) -> ShockDetection:
    """Detect price shock inside a sliding trade window."""
    if len(window_ticks) < 2:
        return ShockDetection(shock=False)

    prices = [t.price for t in window_ticks]
    peak = max(prices)
    floor = min(prices)
    if peak <= 0:
        return ShockDetection(shock=False)

    drop_pct = (peak - floor) / peak
    drop_abs = peak - floor
    if drop_pct >= min_drop_pct and drop_abs >= min_drop_abs:
        return ShockDetection(
            shock=True,
            peak=peak,
            floor=floor,
            depth=drop_abs,
            pre_price=peak,
        )
    return ShockDetection(shock=False)


def classify_league(slug: str, cfg: ClassifierConfig) -> str:
    s = slug.lower()
    if any(token in s for token in cfg.deep_slugs):
        return "deep"
    if any(token in s for token in cfg.thin_slugs):
        return "thin"
    return "unknown"


def classify_favoritism(pre_price: float, cfg: ClassifierConfig) -> str:
    f = cfg.favoritism
    if pre_price >= f.heavy_fav_min:
        return "heavy_fav"
    if pre_price >= f.moderate_fav_min:
        return "moderate_fav"
    if pre_price >= f.slight_fav_min:
        return "slight_fav"
    if pre_price >= f.balanced_min:
        return "balanced"
    return "underdog"


def classify_book_depth(bids: tuple[BookLevel, ...], cfg: ClassifierConfig) -> str:
    if not bids:
        return "balanced"
    total = sum(level.size for level in bids)
    if total <= 0:
        return "balanced"
    top3 = sum(level.size for level in bids[:3])
    ratio = top3 / total
    if ratio >= cfg.top_heavy_ratio:
        return "top_heavy"
    if ratio >= cfg.balanced_ratio:
        return "balanced"
    return "deep"


def classify_match_time(elapsed_ms: int, cfg: ClassifierConfig) -> str:
    minutes = elapsed_ms / 60_000
    if minutes <= cfg.early_max_min:
        return "early"
    if minutes <= cfg.mid_max_min:
        return "mid"
    if minutes <= cfg.late_max_min:
        return "late"
    return "final"


def classify_goal_state(goal_diff: int, cfg: ClassifierConfig) -> str:
    diff = abs(goal_diff)
    if diff >= cfg.blowout_diff:
        return "blowout"
    if diff == 2:
        return "two"
    if diff == 1:
        return "one"
    return "level"


def bucket_key(ctx: ShockContext, cfg: ClassifierConfig) -> str:
    return "|".join(
        [
            classify_league(ctx.slug, cfg),
            classify_favoritism(ctx.pre_price, cfg),
            classify_book_depth(ctx.bids, cfg),
            classify_match_time(ctx.elapsed_ms, cfg),
            classify_goal_state(ctx.goal_diff, cfg),
        ]
    )


def compute_percentiles(
    depths_cents: tuple[float, ...],
    keys: tuple[int, ...],
) -> dict[int, float]:
    """Linear-interpolation percentiles (stdlib only)."""
    if not depths_cents:
        return {}
    sorted_depths = sorted(depths_cents)
    n = len(sorted_depths)
    out: dict[int, float] = {}
    for p in keys:
        if n == 1:
            out[p] = sorted_depths[0]
            continue
        rank = (p / 100.0) * (n - 1)
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        frac = rank - lo
        out[p] = sorted_depths[lo] * (1 - frac) + sorted_depths[hi] * frac
    return out


def resolve_percentiles_for_bucket(
    bucket: str,
    historical_depths: dict[str, list[float]],
    cfg: MatchShockConfig,
) -> dict[int, float]:
    depths = historical_depths.get(bucket) or []
    keys = cfg.distribution.percentile_keys
    if len(depths) >= cfg.distribution.min_samples_per_bucket:
        return compute_percentiles(tuple(depths), keys)
    return dict(cfg.distribution.default_percentiles_cents)


def build_ladder(
    pre_price: float,
    percentiles_cents: dict[int, float],
    ladder: LadderConfig,
) -> tuple[LadderOrder, ...]:
    orders: list[LadderOrder] = []
    for pct, weight in sorted(ladder.weights.items()):
        depth_cents = percentiles_cents.get(pct)
        if depth_cents is None:
            continue
        limit_price = round(pre_price - depth_cents / 100.0, 2)
        orders.append(
            LadderOrder(
                percentile=pct,
                limit_price=max(limit_price, 0.01),
                size_usd=ladder.capital_usd * weight,
                weight=weight,
            )
        )
    return tuple(orders)


def plan_ladder(
    ctx: ShockContext,
    historical_depths: dict[str, list[float]],
    cfg: MatchShockConfig,
) -> LadderPlan:
    key = bucket_key(ctx, cfg.classifiers)
    pcts = resolve_percentiles_for_bucket(key, historical_depths, cfg)
    orders = build_ladder(ctx.pre_price, pcts, cfg.ladder)
    recovery = round(ctx.pre_price - cfg.ladder.recovery_target_cents / 100.0, 2)
    return LadderPlan(
        bucket_key=key,
        pre_price=ctx.pre_price,
        percentiles_cents=pcts,
        orders=orders,
        recovery_target_price=max(recovery, 0.01),
    )


def bucket_passes_backtest_filter(bucket: str, cfg: MatchShockConfig) -> bool:
    parts = bucket.split("|")
    if len(parts) != 5:
        return False
    league, favoritism, *_rest = parts
    bt = cfg.backtest
    if bt.allowed_league_tiers and league not in bt.allowed_league_tiers:
        return False
    if bt.allowed_favoritism and favoritism not in bt.allowed_favoritism:
        return False
    return True


def slug_in_scope(slug: str, cfg: MatchShockConfig) -> bool:
    s = slug.lower()
    if cfg.markets.blocked_slug_patterns and any(
        pat in s for pat in cfg.markets.blocked_slug_patterns
    ):
        return False
    if not cfg.markets.slug_patterns:
        return True
    return any(pat in s for pat in cfg.markets.slug_patterns)


def simulate_paper_fill(
    plan: LadderPlan,
    post_shock_low: float,
) -> LadderOrder | None:
    """Return deepest filled ladder rung at or above post-shock low (price touch)."""
    filled: LadderOrder | None = None
    for order in plan.orders:
        if post_shock_low <= order.limit_price:
            filled = order
    return filled


def simulate_recovery_pnl(
    fill: LadderOrder,
    exit_price: float,
) -> float:
    if fill.limit_price <= 0:
        return 0.0
    shares = fill.size_usd / fill.limit_price
    return shares * exit_price - fill.size_usd


def horizon_exit_price(
    ticks: list,
    shock_ts_ms: int,
    *,
    recovery_target: float,
    pre_price: float,
    horizon_ms: int,
) -> float:
    """Mark-to-market exit within horizon — can be below entry (honest paper)."""
    end = shock_ts_ms + max(horizon_ms, 1)
    window = [t.price for t in ticks if shock_ts_ms <= t.ts_ms <= end]
    if not window:
        return min(recovery_target, pre_price)
    peak = max(window)
    return min(peak, recovery_target, pre_price)


def ladder_plan_to_dict(plan: LadderPlan) -> dict[str, Any]:
    return {
        "bucket_key": plan.bucket_key,
        "pre_price": plan.pre_price,
        "percentiles_cents": plan.percentiles_cents,
        "recovery_target_price": plan.recovery_target_price,
        "orders": [
            {
                "percentile": o.percentile,
                "limit_price": o.limit_price,
                "size_usd": o.size_usd,
                "weight": o.weight,
            }
            for o in plan.orders
        ],
    }
