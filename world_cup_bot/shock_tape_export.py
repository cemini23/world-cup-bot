"""Data API trade history → match-shock JSONL tapes."""

from __future__ import annotations

import json
from pathlib import Path

from world_cup_bot.data_api_client import iter_market_trades, trade_to_shock_tick
from world_cup_bot.match_market_discovery import MatchMarket


def export_markets(
    markets: list[MatchMarket],
    out_dir: Path,
    *,
    max_trades_per_market: int | None,
    data_api: str,
    combined_name: str = "combined.jsonl",
) -> dict[str, int]:
    stats = {"markets": 0, "trades": 0, "markets_with_trades": 0}
    out_dir.mkdir(parents=True, exist_ok=True)
    combined = out_dir / combined_name
    per_slug = out_dir / "by_slug"
    per_slug.mkdir(exist_ok=True)

    with combined.open("w", encoding="utf-8") as combo_f:
        for market in markets:
            stats["markets"] += 1
            slug_trades = 0
            slug_path = per_slug / f"{market.slug}.jsonl"
            with slug_path.open("w", encoding="utf-8") as slug_f:
                for row in iter_market_trades(
                    market.condition_id,
                    max_trades=max_trades_per_market,
                    data_api=data_api,
                ):
                    tick = trade_to_shock_tick(row, slug=market.slug)
                    line = json.dumps(tick, separators=(",", ":")) + "\n"
                    slug_f.write(line)
                    combo_f.write(line)
                    slug_trades += 1
                    stats["trades"] += 1
            if slug_trades:
                stats["markets_with_trades"] += 1
            else:
                slug_path.unlink(missing_ok=True)

    return stats
