#!/usr/bin/env python3
"""Export pmxt (or normalized) history → match-shock JSONL tapes.

Accepts pmxt archive exports, sidecar dumps, or fixture-format JSONL. Writes one
combined tape or per-slug files for run_bucket_backtest.py.

Input formats (auto-detected per line or via --format):

  pmxt_event — unified pmxt JSONL:
    {"event":"trade","slug":"...","timestamp":1710000000000,"price":0.30,...}
    {"event":"orderbook","slug":"...","timestamp":...,"bids":[...],"asks":[...]}

  pmxt_trade — legacy trade row:
    {"timestamp":1710000000000,"price":0.30,"slug":"...","side":"buy"}

  pmxt_book — orderbook snapshot:
    {"timestamp":...,"slug":"...","bids":[{"price":0.29,"size":100}],...}

  pmxt_candle — OHLCV (pmxt fetchOHLCV):
    {"timestamp":...,"open":0.3,"high":0.31,"low":0.28,"close":0.29,"slug":"..."}

  shock_tick — already normalized (pass-through)

See scripts/shock_backtest/README.md and OSINT Architecture - match_shock_pmxt_backtest.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_cup_bot.match_shock import BookLevel  # noqa: E402
from world_cup_bot.match_shock_config import load_match_shock_config  # noqa: E402

# Default slug filter patterns from shock_match.yaml (overridden by --include/--exclude)
_DEFAULT_INCLUDE = ("world-cup", "fifa", "epl", "ucl", "champions-league", "la-liga", "vs-")
_DEFAULT_EXCLUDE = ("advance", "group-winner", "to-win-the-world-cup", "knockout")


@dataclass
class RawObs:
    ts_ms: int
    slug: str
    price: float | None = None
    bids: tuple[BookLevel, ...] = ()
    elapsed_ms: int = 0
    goal_diff: int = 0


@dataclass
class ExportStats:
    lines_in: int = 0
    lines_skipped: int = 0
    slugs: set[str] | None = None
    ticks_out: int = 0

    def __post_init__(self) -> None:
        if self.slugs is None:
            self.slugs = set()


def _slug_allowed(slug: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    s = slug.lower()
    if exclude and any(p in s for p in exclude):
        return False
    if not include:
        return True
    return any(p in s for p in include)


def _parse_levels(raw: list[Any] | None) -> tuple[BookLevel, ...]:
    if not raw:
        return ()
    out: list[BookLevel] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            out.append(BookLevel(price=float(row["price"]), size=float(row["size"])))
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(out)


def _infer_slug(row: dict[str, Any]) -> str | None:
    for key in ("slug", "market_slug", "marketSlug", "symbol"):
        val = row.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    meta = row.get("metadata") or row.get("meta") or {}
    if isinstance(meta, dict):
        for key in ("slug", "market_slug"):
            val = meta.get(key)
            if val and isinstance(val, str):
                return val.strip()
    return None


def _infer_ts_ms(row: dict[str, Any]) -> int | None:
    for key in ("ts_ms", "timestamp", "ts", "time"):
        val = row.get(key)
        if val is None:
            continue
        try:
            ts = int(val)
            if ts < 10_000_000_000:
                ts *= 1000
            return ts
        except (TypeError, ValueError):
            continue
    return None


def _parse_pmxt_trade(row: dict[str, Any]) -> RawObs | None:
    slug = _infer_slug(row)
    ts = _infer_ts_ms(row)
    if not slug or ts is None:
        return None
    try:
        price = float(row.get("price") or row.get("avg_price") or row.get("avgPrice"))
    except (TypeError, ValueError):
        return None
    return RawObs(ts_ms=ts, slug=slug, price=price)


def _parse_pmxt_book(row: dict[str, Any]) -> RawObs | None:
    slug = _infer_slug(row)
    ts = _infer_ts_ms(row)
    if not slug or ts is None:
        return None
    bids = _parse_levels(row.get("bids"))
    asks = _parse_levels(row.get("asks"))
    mid = row.get("mid")
    price: float | None = None
    if mid is not None:
        try:
            price = float(mid)
        except (TypeError, ValueError):
            price = None
    if price is None and bids and asks:
        price = (bids[0].price + asks[0].price) / 2.0
    elif price is None and bids:
        price = bids[0].price
    elif price is None and asks:
        price = asks[0].price
    return RawObs(ts_ms=ts, slug=slug, price=price, bids=bids)


def _parse_pmxt_candle(row: dict[str, Any]) -> RawObs | None:
    slug = _infer_slug(row)
    ts = _infer_ts_ms(row)
    if not slug or ts is None:
        return None
    for key in ("close", "c", "price"):
        if key in row:
            try:
                return RawObs(ts_ms=ts, slug=slug, price=float(row[key]))
            except (TypeError, ValueError):
                break
    return None


def _parse_pmxt_event(row: dict[str, Any]) -> RawObs | None:
    ev = str(row.get("event") or row.get("type") or "").lower()
    if ev in ("trade", "trades"):
        return _parse_pmxt_trade(row)
    if ev in ("orderbook", "book", "l2"):
        return _parse_pmxt_book(row)
    if ev in ("candle", "ohlcv"):
        return _parse_pmxt_candle(row)
    if "bids" in row or "asks" in row:
        return _parse_pmxt_book(row)
    if "price" in row and "amount" in row:
        return _parse_pmxt_trade(row)
    if "close" in row:
        return _parse_pmxt_candle(row)
    return None


def _parse_shock_tick(row: dict[str, Any]) -> RawObs | None:
    slug = _infer_slug(row)
    ts = _infer_ts_ms(row)
    if not slug or ts is None:
        return None
    try:
        price = float(row["price"])
    except (KeyError, TypeError, ValueError):
        return None
    bids = _parse_levels(row.get("bids"))
    return RawObs(
        ts_ms=ts,
        slug=slug,
        price=price,
        bids=bids,
        elapsed_ms=int(row.get("elapsed_ms") or 0),
        goal_diff=int(row.get("goal_diff") or 0),
    )


PARSERS = {
    "auto": None,
    "pmxt_event": _parse_pmxt_event,
    "pmxt_trade": _parse_pmxt_trade,
    "pmxt_book": _parse_pmxt_book,
    "pmxt_candle": _parse_pmxt_candle,
    "shock_tick": _parse_shock_tick,
}


def _auto_parse(row: dict[str, Any]) -> RawObs | None:
    for fn in (
        _parse_shock_tick,
        _parse_pmxt_event,
        _parse_pmxt_book,
        _parse_pmxt_trade,
        _parse_pmxt_candle,
    ):
        obs = fn(row)
        if obs is not None:
            return obs
    return None


def iter_observations(
    path: Path,
    *,
    fmt: str,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    stats: ExportStats,
) -> Iterator[RawObs]:
    parser = PARSERS.get(fmt)
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            stats.lines_in += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                stats.lines_skipped += 1
                continue
            if not isinstance(row, dict):
                stats.lines_skipped += 1
                continue
            obs = parser(row) if parser else _auto_parse(row)
            if obs is None:
                stats.lines_skipped += 1
                continue
            if not _slug_allowed(obs.slug, include, exclude):
                stats.lines_skipped += 1
                continue
            stats.slugs.add(obs.slug)
            yield obs


def merge_books_by_slug(
    observations: Iterator[RawObs],
) -> Iterator[RawObs]:
    """Carry forward latest book snapshot onto trade ticks."""
    last_bids: dict[str, tuple[BookLevel, ...]] = {}
    for obs in observations:
        if obs.bids:
            last_bids[obs.slug] = obs.bids
        bids = obs.bids or last_bids.get(obs.slug, ())
        if obs.price is None:
            continue
        yield RawObs(
            ts_ms=obs.ts_ms,
            slug=obs.slug,
            price=obs.price,
            bids=bids,
            elapsed_ms=obs.elapsed_ms,
            goal_diff=obs.goal_diff,
        )


def obs_to_tick_line(obs: RawObs) -> str:
    payload: dict[str, Any] = {
        "ts_ms": obs.ts_ms,
        "price": obs.price,
        "slug": obs.slug,
        "elapsed_ms": obs.elapsed_ms,
        "goal_diff": obs.goal_diff,
    }
    if obs.bids:
        payload["bids"] = [{"price": b.price, "size": b.size} for b in obs.bids]
    return json.dumps(payload, separators=(",", ":"))


def export_tapes(
    inputs: list[Path],
    out_dir: Path,
    *,
    combined_name: str = "combined.jsonl",
    per_slug: bool,
    fmt: str,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
) -> ExportStats:
    stats = ExportStats()
    by_slug: dict[str, list[str]] = defaultdict(list)
    combined: list[str] = []

    for inp in inputs:
        if inp.is_dir():
            files = sorted(inp.glob("**/*.jsonl"))
        else:
            files = [inp]
        for path in files:
            obs_iter = iter_observations(
                path, fmt=fmt, include=include, exclude=exclude, stats=stats
            )
            for obs in merge_books_by_slug(obs_iter):
                line = obs_to_tick_line(obs)
                combined.append(line)
                by_slug[obs.slug].append(line)
                stats.ticks_out += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    combined_path = out_dir / combined_name
    combined_path.write_text("\n".join(combined) + ("\n" if combined else ""), encoding="utf-8")

    if per_slug:
        slug_dir = out_dir / "by_slug"
        slug_dir.mkdir(parents=True, exist_ok=True)
        for slug, lines in by_slug.items():
            safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", slug)[:120]
            (slug_dir / f"{safe}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return stats


def _load_patterns_from_config(config_path: Path | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        cfg = load_match_shock_config(config_path)
        inc = cfg.markets.slug_patterns
        exc = cfg.markets.blocked_slug_patterns
        return inc, exc
    except OSError:
        return _DEFAULT_INCLUDE, _DEFAULT_EXCLUDE


def main() -> int:
    parser = argparse.ArgumentParser(description="Export pmxt history → shock JSONL tapes")
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="JSONL files or directories (recursive *.jsonl)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/local/shock_tapes"),
        help="Output directory",
    )
    parser.add_argument(
        "--format",
        choices=list(PARSERS.keys()),
        default="auto",
        help="Input line format (default: auto-detect)",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=None,
        help="Slug substring filter (repeatable); default from shock_match.yaml",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Slug substring exclude (repeatable)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="shock_match.yaml for slug filters",
    )
    parser.add_argument(
        "--per-slug",
        action="store_true",
        help="Also write out-dir/by_slug/<slug>.jsonl",
    )
    parser.add_argument(
        "--combined-name",
        default="combined.jsonl",
        help="Combined output filename",
    )
    args = parser.parse_args()

    cfg_inc, cfg_exc = _load_patterns_from_config(args.config)
    include = tuple(args.include) if args.include else cfg_inc or _DEFAULT_INCLUDE
    exclude = tuple(args.exclude) if args.exclude else cfg_exc or _DEFAULT_EXCLUDE

    stats = export_tapes(
        args.inputs,
        args.out_dir,
        combined_name=args.combined_name,
        per_slug=args.per_slug,
        fmt=args.format,
        include=include,
        exclude=exclude,
    )

    summary = {
        "lines_in": stats.lines_in,
        "lines_skipped": stats.lines_skipped,
        "ticks_out": stats.ticks_out,
        "slugs": sorted(stats.slugs or []),
        "out_dir": str(args.out_dir.resolve()),
    }
    print(json.dumps(summary, indent=2))
    manifest = args.out_dir / "export_manifest.json"
    manifest.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if stats.ticks_out > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
