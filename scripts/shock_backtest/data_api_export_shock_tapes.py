#!/usr/bin/env python3
"""Export Polymarket Data API trade history → match-shock JSONL tapes.

Dome API reached EOL 2026-04-28; this script uses the public Data API instead:
  GET https://data-api.polymarket.com/trades?market={conditionId}

Workflow:
  1. world-cup-bot match-shock-discover --out data/local/match_markets.json
  2. python scripts/shock_backtest/data_api_export_shock_tapes.py \\
       --discovery data/local/match_markets.json --out-dir data/local/shock_tapes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_cup_bot.data_api_client import DEFAULT_DATA_API  # noqa: E402
from world_cup_bot.match_market_discovery import (  # noqa: E402
    discover_match_markets,
    load_discovery_json,
    write_discovery_json,
)
from world_cup_bot.shock_tape_export import export_markets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Data API → shock JSONL export")
    parser.add_argument(
        "--discovery",
        type=Path,
        help="JSON from match-shock-discover (else run live Gamma discover)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/local/shock_tapes"),
    )
    parser.add_argument(
        "--discover-out",
        type=Path,
        default=None,
        help="When discovering live, also write discovery JSON here",
    )
    parser.add_argument("--gamma-url", default="https://gamma-api.polymarket.com")
    parser.add_argument("--max-trades", type=int, default=5000)
    args = parser.parse_args()

    if args.discovery and args.discovery.is_file():
        markets = load_discovery_json(args.discovery)
    else:
        markets = discover_match_markets(args.gamma_url.rstrip("/"))
        if args.discover_out:
            write_discovery_json(markets, args.discover_out)

    if not markets:
        print(json.dumps({"error": "no match markets discovered", "stats": {}}, indent=2))
        return 1

    stats = export_markets(
        markets,
        args.out_dir,
        max_trades_per_market=args.max_trades,
        data_api=DEFAULT_DATA_API,
    )
    print(json.dumps({"export": stats, "out_dir": str(args.out_dir.resolve())}, indent=2))
    return 0 if stats["trades"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
