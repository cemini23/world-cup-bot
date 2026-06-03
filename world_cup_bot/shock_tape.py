"""Shared shock tape JSONL parsing and shock scan (Module 8)."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from world_cup_bot.match_shock import (
    BookLevel,
    PriceTick,
    ShockContext,
    bucket_passes_backtest_filter,
    detect_shock,
    plan_ladder,
    slug_in_scope,
)
from world_cup_bot.match_shock_config import MatchShockConfig


@dataclass
class ParsedTick:
    ts_ms: int
    price: float
    slug: str
    elapsed_ms: int
    goal_diff: int
    bids: tuple[BookLevel, ...]


def parse_tick_line(raw: dict) -> ParsedTick | None:
    try:
        ts_ms = int(raw["ts_ms"])
        price = float(raw["price"])
        slug = str(raw["slug"])
    except (KeyError, TypeError, ValueError):
        return None
    elapsed_ms = int(raw.get("elapsed_ms") or 0)
    goal_diff = int(raw.get("goal_diff") or 0)
    bids_raw = raw.get("bids") or []
    bids: list[BookLevel] = []
    for row in bids_raw:
        try:
            bids.append(BookLevel(price=float(row["price"]), size=float(row["size"])))
        except (KeyError, TypeError, ValueError):
            continue
    return ParsedTick(
        ts_ms=ts_ms,
        price=price,
        slug=slug,
        elapsed_ms=elapsed_ms,
        goal_diff=goal_diff,
        bids=tuple(bids),
    )


def load_ticks(path: Path) -> list[ParsedTick]:
    ticks: list[ParsedTick] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            tick = parse_tick_line(raw)
            if tick is not None:
                ticks.append(tick)
    return ticks


def group_by_slug(ticks: list[ParsedTick]) -> dict[str, list[ParsedTick]]:
    out: dict[str, list[ParsedTick]] = defaultdict(list)
    for t in ticks:
        out[t.slug].append(t)
    for slug in out:
        out[slug].sort(key=lambda x: x.ts_ms)
    return dict(out)


def scan_shocks(
    ticks: list[ParsedTick],
    cfg: MatchShockConfig,
) -> list[tuple[ParsedTick, ShockContext, float]]:
    """Return (trigger_tick, context, depth_cents) for each detected shock."""
    det = cfg.detection
    window_ms = det.window_ms
    cooldown_ms = det.cooldown_ms
    results: list[tuple[ParsedTick, ShockContext, float]] = []
    last_shock_ts: int | None = None

    for i, tick in enumerate(ticks):
        if not slug_in_scope(tick.slug, cfg):
            continue
        window_start = tick.ts_ms - window_ms
        window = [
            PriceTick(ts_ms=t.ts_ms, price=t.price)
            for t in ticks[: i + 1]
            if t.ts_ms >= window_start
        ]
        shock = detect_shock(
            tuple(window),
            min_drop_pct=det.min_drop_pct,
            min_drop_abs=det.min_drop_abs,
        )
        if not shock.shock or shock.pre_price is None or shock.depth is None:
            continue
        if last_shock_ts is not None and tick.ts_ms - last_shock_ts < cooldown_ms:
            continue
        ctx = ShockContext(
            slug=tick.slug,
            pre_price=shock.pre_price,
            bids=tick.bids,
            elapsed_ms=tick.elapsed_ms,
            goal_diff=tick.goal_diff,
        )
        results.append((tick, ctx, shock.depth * 100.0))
        last_shock_ts = tick.ts_ms
    return results


def build_distributions(
    shocks: list[tuple[ParsedTick, ShockContext, float]],
    cfg: MatchShockConfig,
) -> dict[str, list[float]]:
    depths: dict[str, list[float]] = defaultdict(list)
    for _tick, ctx, depth_cents in shocks:
        plan = plan_ladder(ctx, depths, cfg)
        if not bucket_passes_backtest_filter(plan.bucket_key, cfg):
            continue
        depths[plan.bucket_key].append(depth_cents)
    return dict(depths)


def replay_paper(
    by_slug: dict[str, list[ParsedTick]],
    historical_depths: dict[str, list[float]],
    cfg: MatchShockConfig,
) -> dict[str, float]:
    """Replay shocks with frozen distribution file; return aggregate stats."""
    from world_cup_bot.match_shock import (
        bucket_passes_backtest_filter,
        plan_ladder,
        simulate_paper_fill,
        simulate_recovery_pnl,
    )

    wins = 0
    losses = 0
    total_pnl = 0.0

    for _slug, ticks in by_slug.items():
        shocks = scan_shocks(ticks, cfg)
        for tick, ctx, _depth_cents in shocks:
            plan = plan_ladder(ctx, historical_depths, cfg)
            if not bucket_passes_backtest_filter(plan.bucket_key, cfg):
                continue
            post_low = min(t.price for t in ticks if t.ts_ms >= tick.ts_ms)
            fill = simulate_paper_fill(plan, post_low)
            if fill is None:
                continue
            exit_price = min(plan.recovery_target_price, ctx.pre_price)
            pnl = simulate_recovery_pnl(fill, exit_price)
            total_pnl += pnl
            if pnl > 0:
                wins += 1
            else:
                losses += 1

    n = wins + losses
    return {
        "trades": float(n),
        "wins": float(wins),
        "losses": float(losses),
        "win_rate": (wins / n) if n else 0.0,
        "total_pnl_usd": total_pnl,
        "window_ms": float(cfg.detection.window_ms),
    }
