#!/usr/bin/env python3
"""Build bucket depth distributions and replay paper PnL from trade JSONL.

Input schema (one object per line):
  {"ts_ms": int, "price": float, "slug": str,
   "elapsed_ms": int (optional), "goal_diff": int (optional),
   "bids": [{"price": float, "size": float}, ...] (optional)}

Data sources:
  - pmxt 1TB Polymarket orderbook archive (subset → trade tape export)
  - CLOB WS capture during WC (future)
  - Dome API historical trades (optional)

See scripts/shock_backtest/README.md and OSINT wiki match_shock_pmxt_backtest.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_cup_bot.match_shock import (  # noqa: E402
    BookLevel,
    PriceTick,
    ShockContext,
    bucket_passes_backtest_filter,
    detect_shock,
    plan_ladder,
    simulate_paper_fill,
    simulate_recovery_pnl,
    slug_in_scope,
)
from world_cup_bot.match_shock_config import MatchShockConfig, load_match_shock_config  # noqa: E402


@dataclass
class ParsedTick:
    ts_ms: int
    price: float
    slug: str
    elapsed_ms: int
    goal_diff: int
    bids: tuple[BookLevel, ...]


def _parse_line(raw: dict) -> ParsedTick | None:
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
            tick = _parse_line(raw)
            if tick is not None:
                ticks.append(tick)
    return ticks


def group_by_slug(ticks: list[ParsedTick]) -> dict[str, list[ParsedTick]]:
    out: dict[str, list[ParsedTick]] = defaultdict(list)
    for t in ticks:
        out[t.slug].append(t)
    for slug in out:
        out[slug].sort(key=lambda x: x.ts_ms)
    return out


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
    wins = 0
    losses = 0
    total_pnl = 0.0
    det = cfg.detection

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
        "window_ms": float(det.window_ms),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Match-shock bucket backtest")
    parser.add_argument(
        "trades_jsonl",
        type=Path,
        help="Trade tape JSONL (see README for schema)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config/shock_match.yaml",
    )
    parser.add_argument(
        "--out-distributions",
        type=Path,
        default=None,
        help="Write bucket→depths JSON for live lookup",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="Run paper replay after building distributions",
    )
    args = parser.parse_args()

    cfg = load_match_shock_config(args.config)
    ticks = load_ticks(args.trades_jsonl)
    if not ticks:
        print("No ticks loaded", file=sys.stderr)
        return 1

    by_slug = group_by_slug(ticks)
    all_shocks: list[tuple[ParsedTick, ShockContext, float]] = []
    for slug_ticks in by_slug.values():
        all_shocks.extend(scan_shocks(slug_ticks, cfg))

    depths = build_distributions(all_shocks, cfg)
    summary = {
        "markets": len(by_slug),
        "ticks": len(ticks),
        "shocks_detected": len(all_shocks),
        "buckets_with_data": len(depths),
        "bucket_sample_counts": {k: len(v) for k, v in sorted(depths.items())},
    }
    print(json.dumps(summary, indent=2))

    if args.out_distributions:
        args.out_distributions.parent.mkdir(parents=True, exist_ok=True)
        args.out_distributions.write_text(json.dumps(depths, indent=2), encoding="utf-8")
        print(f"Wrote distributions → {args.out_distributions}")

    if args.replay:
        stats = replay_paper(by_slug, depths, cfg)
        print(json.dumps({"replay": stats}, indent=2))
        if stats["trades"] > 0 and stats["win_rate"] < cfg.backtest.min_recovery_rate:
            print(
                f"WARN: win_rate {stats['win_rate']:.2%} below gate "
                f"{cfg.backtest.min_recovery_rate:.2%}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
