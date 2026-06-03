#!/usr/bin/env python3
"""Convert pmxt Polymarket v2 hourly parquet → pmxt_event JSONL (football filter).

Requires: pip install pyarrow  (or pyarrow+pandas on librarian)

Usage:
  python pmxt_parquet_to_jsonl.py --inspect path/to/file.parquet
  python pmxt_parquet_to_jsonl.py file.parquet --out raw/pmxt_events.jsonl --append
  python pmxt_parquet_to_jsonl.py staging/*.parquet --out raw/pmxt_events.jsonl

Schema varies by archive version — run --inspect on first download. Common columns:
  slug / market_slug / event_slug, timestamp / dt, price / mid, bids / asks (list or JSON str)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_cup_bot.match_shock_config import load_match_shock_config  # noqa: E402

SLUG_COLUMNS = ("slug", "market_slug", "event_slug", "marketSlug", "market_slug_str")
CONDITION_COLUMNS = ("market", "condition_id", "conditionId", "conditionid")
TS_COLUMNS = ("timestamp_received", "timestamp", "ts_ms", "ts", "datetime", "dt", "time")
PRICE_COLUMNS = ("price", "mid", "best_bid", "bestBid", "close", "last_price")
BID_COLUMNS = ("bids", "bid_levels", "bidLevels")
ASK_COLUMNS = ("asks", "ask_levels", "askLevels")
GAMMA_API = "https://gamma-api.polymarket.com/markets"
GAMMA_BATCH_SIZE = 40
GAMMA_SLEEP_S = 0.02
READ_BATCH_SIZE = 200_000


class SlugResolver:
    """Map Polymarket condition_id → slug via Gamma API (cached)."""

    def __init__(self, *, gamma_api: str = GAMMA_API, sleep_s: float = GAMMA_SLEEP_S) -> None:
        self.gamma_api = gamma_api
        self.sleep_s = sleep_s
        self._cache: dict[str, str | None] = {}

    def resolve(self, condition_id: str) -> str | None:
        key = condition_id.lower()
        if key in self._cache:
            return self._cache[key]
        slug = self._fetch_slug(key)
        self._cache[key] = slug
        if self.sleep_s:
            time.sleep(self.sleep_s)
        return slug

    def _fetch_slug(self, condition_id: str) -> str | None:
        rows = _gamma_fetch_markets([condition_id], gamma_api=self.gamma_api)
        if not rows:
            return None
        slug = rows[0].get("slug")
        return str(slug).strip() if slug else None


class PrefetchedSlugResolver:
    """O(1) slug lookup from a pre-built condition_id → slug map."""

    def __init__(self, slug_by_condition: dict[str, str]) -> None:
        self._map = {k.lower(): v for k, v in slug_by_condition.items()}

    def resolve(self, condition_id: str) -> str | None:
        return self._map.get(condition_id.lower())


def _gamma_fetch_markets(
    condition_ids: list[str],
    *,
    gamma_api: str = GAMMA_API,
) -> list[dict[str, Any]]:
    if not condition_ids:
        return []
    params: list[tuple[str, str]] = [("condition_ids", cid) for cid in condition_ids]
    params.append(("limit", str(max(len(condition_ids), 1))))
    url = f"{gamma_api}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "cemini-wc-bot-pmxt-etl/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def prefetch_football_slugs(
    condition_ids: set[str],
    *,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    batch_size: int = GAMMA_BATCH_SIZE,
    sleep_s: float = GAMMA_SLEEP_S,
) -> dict[str, str]:
    """Batch-resolve condition_ids via Gamma; return football condition_id → slug."""
    football: dict[str, str] = {}
    ids = sorted(condition_ids)
    for start in range(0, len(ids), batch_size):
        chunk = ids[start : start + batch_size]
        found: set[str] = set()
        for row in _gamma_fetch_markets(chunk):
            cid = str(row.get("conditionId") or row.get("condition_id") or "").lower()
            slug = str(row.get("slug") or "").strip()
            if not cid or not slug:
                continue
            found.add(cid)
            if _slug_allowed(slug, include, exclude):
                football[cid] = slug
        for cid in chunk:
            key = cid.lower()
            if key in found:
                continue
            for row in _gamma_fetch_markets([cid]):
                slug = str(row.get("slug") or "").strip()
                if slug and _slug_allowed(slug, include, exclude):
                    football[key] = slug
                break
        if sleep_s and start + batch_size < len(ids):
            time.sleep(sleep_s)
    return football


def collect_unique_condition_ids(path: Path) -> set[str]:
    """Pass 1 — scan market/condition_id column only (memory-safe on large files)."""
    pq = _require_pyarrow()
    pf = pq.ParquetFile(path)
    colmap = build_column_map(pf.schema_arrow.names)
    cond_col = colmap.get("condition_id")
    if not cond_col:
        raise ValueError(f"No condition_id column in {path.name}")
    unique: set[str] = set()
    for batch in pf.iter_batches(batch_size=READ_BATCH_SIZE, columns=[cond_col]):
        column = batch.column(0)
        for i in range(batch.num_rows):
            cid = _normalize_condition_id(column[i].as_py())
            if cid:
                unique.add(cid.lower())
    return unique


def _require_pyarrow():
    try:
        import pyarrow.parquet as pq  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "pyarrow required: pip install pyarrow\n"
            "On librarian: pip install pyarrow --break-system-packages (or venv)"
        ) from exc
    import pyarrow.parquet as pq

    return pq


def _first_column(names: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {n.lower(): n for n in names}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _parse_levels(val: Any) -> list[dict[str, float]] | None:
    if val is None:
        return None
    if isinstance(val, str):
        try:
            val = json.loads(val)
        except json.JSONDecodeError:
            return None
    if isinstance(val, list):
        out: list[dict[str, float]] = []
        for row in val:
            if isinstance(row, dict) and "price" in row:
                try:
                    out.append({"price": float(row["price"]), "size": float(row.get("size", 0))})
                except (TypeError, ValueError):
                    continue
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                try:
                    out.append({"price": float(row[0]), "size": float(row[1])})
                except (TypeError, ValueError):
                    continue
        return out or None
    return None


def _slug_allowed(slug: str, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    s = slug.lower()
    if exclude and any(p in s for p in exclude):
        return False
    if not include:
        return True
    return any(p in s for p in include)


def _normalize_condition_id(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, bytes):
        try:
            s = val.decode("utf-8").strip()
            if s.startswith("0x"):
                return s
        except UnicodeDecodeError:
            pass
        return "0x" + val.hex()
    if isinstance(val, str):
        s = val.strip()
        if s.startswith("0x"):
            return s
        if s.startswith("b'") and s.endswith("'"):
            try:
                raw = bytes.fromhex(s[2:-1].replace("0x", ""))
                return "0x" + raw.hex()
            except ValueError:
                return None
    return None


def _row_to_events(
    row: dict[str, Any],
    colmap: dict[str, str | None],
    *,
    slug: str,
) -> list[dict[str, Any]]:
    slug = slug.strip()
    if not slug:
        return []

    ts_col = colmap.get("ts")
    ts_raw = row.get(ts_col) if ts_col else None
    ts_ms: int | None = None
    if ts_raw is not None:
        try:
            if hasattr(ts_raw, "timestamp"):
                ts_ms = int(ts_raw.timestamp() * 1000)
            else:
                ts_ms = int(ts_raw)
                if ts_ms < 10_000_000_000:
                    ts_ms *= 1000
        except (TypeError, ValueError):
            ts_ms = None

    events: list[dict[str, Any]] = []
    base = {"slug": slug}
    if ts_ms is not None:
        base["timestamp"] = ts_ms

    bids_col = colmap.get("bids")
    asks_col = colmap.get("asks")
    bids = _parse_levels(row.get(bids_col)) if bids_col else None
    asks = _parse_levels(row.get(asks_col)) if asks_col else None

    if bids is None and row.get("best_bid") is not None:
        try:
            bids = [{"price": float(row["best_bid"]), "size": 0.0}]
        except (TypeError, ValueError):
            pass
    if asks is None and row.get("best_ask") is not None:
        try:
            asks = [{"price": float(row["best_ask"]), "size": 0.0}]
        except (TypeError, ValueError):
            pass

    price_col = colmap.get("price")
    price = row.get(price_col) if price_col else None
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None

    if bids or asks:
        ob = {**base, "event": "orderbook"}
        if bids:
            ob["bids"] = bids
        if asks:
            ob["asks"] = asks
        if price is not None:
            ob["mid"] = price
        events.append(ob)

    if price is not None:
        events.append({**base, "event": "trade", "price": price})

    # pmxt tick JSON blob
    data_col = colmap.get("data")
    if data_col and row.get(data_col):
        raw = row[data_col]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = None
        if isinstance(raw, dict):
            p = raw.get("price") or raw.get("p")
            if p is not None and ts_ms is not None:
                try:
                    events.append(
                        {
                            "event": "trade",
                            "slug": slug,
                            "timestamp": ts_ms,
                            "price": float(p),
                        }
                    )
                except (TypeError, ValueError):
                    pass

    return events


def build_column_map(column_names: list[str]) -> dict[str, str | None]:
    return {
        "slug": _first_column(column_names, SLUG_COLUMNS),
        "condition_id": _first_column(column_names, CONDITION_COLUMNS),
        "ts": _first_column(column_names, TS_COLUMNS),
        "price": _first_column(column_names, PRICE_COLUMNS),
        "bids": _first_column(column_names, BID_COLUMNS),
        "asks": _first_column(column_names, ASK_COLUMNS),
        "data": _first_column(column_names, ("data", "payload", "raw")),
    }


def _resolve_row_slug(
    row: dict[str, Any],
    colmap: dict[str, str | None],
    resolver: SlugResolver | None,
) -> str | None:
    slug_col = colmap.get("slug")
    if slug_col:
        slug_val = row.get(slug_col)
        if isinstance(slug_val, str) and slug_val.strip():
            return slug_val.strip()
    cond_col = colmap.get("condition_id")
    if cond_col and resolver:
        cid = _normalize_condition_id(row.get(cond_col))
        if cid:
            return resolver.resolve(cid)
    return None


def inspect_parquet(path: Path) -> None:
    pq = _require_pyarrow()
    table = pq.read_table(path).slice(0, 5)
    colmap = build_column_map(table.column_names)
    print(
        json.dumps(
            {"file": str(path), "columns": table.column_names, "colmap": colmap},
            indent=2,
        )
    )
    for i in range(table.num_rows):
        row = {name: table[name][i].as_py() for name in table.column_names}
        print(json.dumps({"row": i, "sample": row}, default=str)[:2000])


def _convert_columns(pf, colmap: dict[str, str | None]) -> list[str]:
    names = set(pf.schema_arrow.names)
    cols: list[str] = []
    for c in (
        colmap.get("condition_id"),
        colmap.get("slug"),
        colmap.get("ts"),
        colmap.get("price"),
        colmap.get("bids"),
        colmap.get("asks"),
        "best_bid",
        "best_ask",
        colmap.get("data"),
    ):
        if c and c in names and c not in cols:
            cols.append(c)
    return cols or list(names)


def iter_parquet_events(
    path: Path,
    *,
    resolver: SlugResolver | PrefetchedSlugResolver | None = None,
    allowed_condition_ids: set[str] | None = None,
) -> Iterator[dict[str, Any]]:
    pq = _require_pyarrow()
    pf = pq.ParquetFile(path)
    colmap = build_column_map(pf.schema_arrow.names)
    if not colmap.get("slug") and not colmap.get("condition_id"):
        raise ValueError(
            f"No slug/condition_id column in {path.name}; "
            f"columns={pf.schema_arrow.names}. Run --inspect first."
        )
    if not colmap.get("slug") and not resolver:
        resolver = SlugResolver()

    columns = _convert_columns(pf, colmap)
    cond_col = colmap.get("condition_id")
    allowed = {c.lower() for c in allowed_condition_ids} if allowed_condition_ids else None

    for batch in pf.iter_batches(batch_size=READ_BATCH_SIZE, columns=columns):
        names = batch.schema.names
        batch_colmap = build_column_map(names)
        cond_idx = names.index(cond_col) if cond_col and cond_col in names else None
        for i in range(batch.num_rows):
            if allowed and cond_idx is not None:
                cid = _normalize_condition_id(batch[cond_idx][i].as_py())
                if not cid or cid.lower() not in allowed:
                    continue
            row = {name: batch[name][i].as_py() for name in names}
            slug = _resolve_row_slug(row, batch_colmap, resolver)
            if not slug:
                continue
            yield from _row_to_events(row, batch_colmap, slug=slug)


def convert_files(
    inputs: list[Path],
    out_path: Path,
    *,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    append: bool,
    resolver: SlugResolver | PrefetchedSlugResolver | None = None,
    prefetch: bool = True,
) -> dict[str, int]:
    stats: dict[str, int] = {
        "files": 0,
        "rows_in": 0,
        "events_out": 0,
        "events_skipped": 0,
        "unique_condition_ids": 0,
        "football_markets": 0,
    }
    mode = "a" if append and out_path.is_file() else "w"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open(mode, encoding="utf-8") as out_f:
        for path in inputs:
            stats["files"] += 1
            slug_resolver = resolver
            allowed_ids: set[str] | None = None

            schema = build_column_map(_require_pyarrow().ParquetFile(path).schema_arrow.names)
            if prefetch and schema.get("condition_id") and not schema.get("slug"):
                unique_ids = collect_unique_condition_ids(path)
                stats["unique_condition_ids"] += len(unique_ids)
                football_map = prefetch_football_slugs(
                    unique_ids,
                    include=include,
                    exclude=exclude,
                )
                stats["football_markets"] += len(football_map)
                if not football_map:
                    continue
                slug_resolver = PrefetchedSlugResolver(football_map)
                allowed_ids = set(football_map.keys())

            if slug_resolver is None:
                slug_resolver = SlugResolver()

            for ev in iter_parquet_events(
                path,
                resolver=slug_resolver,
                allowed_condition_ids=allowed_ids,
            ):
                stats["rows_in"] += 1
                slug = str(ev.get("slug") or "")
                if allowed_ids is None and not _slug_allowed(slug, include, exclude):
                    stats["events_skipped"] += 1
                    continue
                out_f.write(json.dumps(ev, separators=(",", ":")) + "\n")
                stats["events_out"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="pmxt parquet → pmxt_event JSONL")
    parser.add_argument("inputs", nargs="*", type=Path, help="Parquet files")
    parser.add_argument("--out", type=Path, default=Path("data/local/pmxt_raw/pmxt_events.jsonl"))
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--inspect", type=Path, default=None, help="Print schema sample and exit")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--include", action="append", default=None)
    parser.add_argument("--exclude", action="append", default=None)
    parser.add_argument(
        "--no-prefetch",
        action="store_true",
        help="Disable pass-1 unique-id scan + batch Gamma (legacy per-row resolve)",
    )
    args = parser.parse_args()

    if args.inspect:
        inspect_parquet(args.inspect)
        return 0

    if not args.inputs:
        parser.error("provide parquet files or --inspect")

    try:
        cfg = load_match_shock_config(args.config)
        include = tuple(args.include) if args.include else cfg.markets.slug_patterns
        exclude = tuple(args.exclude) if args.exclude else cfg.markets.blocked_slug_patterns
    except OSError:
        include = tuple(args.include or ())
        exclude = tuple(args.exclude or ())

    stats = convert_files(
        args.inputs,
        args.out,
        include=include,
        exclude=exclude,
        append=args.append,
        prefetch=not args.no_prefetch,
    )
    print(json.dumps({"convert": stats, "out": str(args.out.resolve())}, indent=2))
    ok = stats["events_out"] > 0 or stats["football_markets"] > 0 or stats["rows_in"] > 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
