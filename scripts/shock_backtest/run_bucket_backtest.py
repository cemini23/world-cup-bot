#!/usr/bin/env python3
"""Build bucket depth distributions and replay paper PnL from trade JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_cup_bot.match_shock_config import load_match_shock_config  # noqa: E402
from world_cup_bot.shock_tape import (  # noqa: E402
    build_distributions,
    group_by_slug,
    load_ticks,
    replay_paper,
    scan_shocks,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Match-shock bucket backtest")
    parser.add_argument("trades_jsonl", type=Path)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--out-distributions", type=Path, default=None)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()

    cfg = load_match_shock_config(args.config)
    ticks = load_ticks(args.trades_jsonl)
    if not ticks:
        print("No ticks loaded", file=sys.stderr)
        return 1

    by_slug = group_by_slug(ticks)
    all_shocks: list = []
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
