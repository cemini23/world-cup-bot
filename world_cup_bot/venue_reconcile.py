"""Venue CSV vs bot ledger reconcile — blind-spot #2 (Gustafssonkotte rule)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from world_cup_bot.clob_auth import ClobAuth, load_clob_auth, load_maker_address, load_poly_address
from world_cup_bot.clob_rest import fetch_trades
from world_cup_bot.config import Settings
from world_cup_bot.ledger import load_rows

ORDER_ID_HEADERS = (
    "order_id",
    "order id",
    "orderid",
    "id",
    "trade_id",
    "trade id",
)

_RECONCILE_TRADE_STATUSES = frozenset(
    {
        "MATCHED",
        "CONFIRMED",
        "MINED",
        "TRADE_STATUS_MATCHED",
        "TRADE_STATUS_CONFIRMED",
        "TRADE_STATUS_MINED",
    }
)


@dataclass(frozen=True)
class VenueReconcileReport:
    ledger_fill_count: int
    venue_row_count: int
    matched: int
    ledger_only: tuple[str, ...]
    venue_only: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "ledger_fill_count": self.ledger_fill_count,
            "venue_row_count": self.venue_row_count,
            "matched": self.matched,
            "ledger_only_count": len(self.ledger_only),
            "venue_only_count": len(self.venue_only),
            "ledger_only": list(self.ledger_only),
            "venue_only": list(self.venue_only),
        }


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace("_", " ")


def _find_order_id_column(fieldnames: list[str] | None) -> str | None:
    if not fieldnames:
        return None
    normalized = {_normalize_header(h): h for h in fieldnames}
    for candidate in ORDER_ID_HEADERS:
        key = _normalize_header(candidate)
        if key in normalized:
            return normalized[key]
    return None


def load_ledger_fill_order_ids(
    ledger_path: Path,
    *,
    logic_version: str | None = None,
) -> set[str]:
    rows = load_rows(ledger_path)
    return {
        str(r["order_id"])
        for r in rows
        if r.get("event") == "order_fill"
        and r.get("order_id")
        and (logic_version is None or r.get("logic_version") == logic_version)
    }


def _maker_order_ids_from_trades(
    trades: list[dict[str, Any]],
    *,
    condition_ids: set[str] | None = None,
) -> set[str]:
    """Extract maker order_ids from CLOB /data/trades rows."""
    ids: set[str] = set()
    for trade in trades:
        status = str(trade.get("status") or "")
        if status not in _RECONCILE_TRADE_STATUSES:
            continue
        if condition_ids is not None:
            cid = str(trade.get("market") or "")
            if cid and cid not in condition_ids:
                continue
        for maker in trade.get("maker_orders") or []:
            if not isinstance(maker, dict):
                continue
            oid = str(maker.get("order_id") or "").strip()
            if oid:
                ids.add(oid)
    return ids


def fetch_clob_maker_order_ids(
    settings: Settings,
    *,
    after_days: int = 30,
    max_pages: int = 20,
    condition_ids: set[str] | None = None,
    auth: ClobAuth | None = None,
) -> tuple[set[str], int]:
    """Fetch maker order_ids from authenticated GET /data/trades (no CSV export)."""
    auth = auth or load_clob_auth()
    poly_address = load_poly_address()
    maker_address = load_maker_address()
    after_ts = int((datetime.now(UTC) - timedelta(days=after_days)).timestamp())
    trades = fetch_trades(
        settings.clob_url,
        auth,
        poly_address,
        maker_address=maker_address,
        after=after_ts,
        max_pages=max_pages,
    )
    return _maker_order_ids_from_trades(trades, condition_ids=condition_ids), len(trades)


def compare_venue_sets(
    ledger_ids: set[str],
    venue_ids: set[str],
) -> VenueReconcileReport:
    matched = ledger_ids & venue_ids
    return VenueReconcileReport(
        ledger_fill_count=len(ledger_ids),
        venue_row_count=len(venue_ids),
        matched=len(matched),
        ledger_only=tuple(sorted(ledger_ids - venue_ids)),
        venue_only=tuple(sorted(venue_ids - ledger_ids)),
    )


def compare_venue_clob(
    ledger_path: Path,
    settings: Settings,
    *,
    logic_version: str | None = None,
    after_days: int = 30,
    max_pages: int = 20,
    condition_ids: set[str] | None = None,
) -> tuple[VenueReconcileReport, int]:
    """Compare ledger fills to CLOB /data/trades maker order_ids."""
    ledger_ids = load_ledger_fill_order_ids(ledger_path, logic_version=logic_version)
    venue_ids, trade_rows = fetch_clob_maker_order_ids(
        settings,
        after_days=after_days,
        max_pages=max_pages,
        condition_ids=condition_ids,
    )
    return compare_venue_sets(ledger_ids, venue_ids), trade_rows


def backfill_ledger_from_clob(
    settings: Settings,
    *,
    after_days: int = 30,
) -> dict[str, Any]:
    """Run one REST reconcile pass to append venue-confirmed fills WS missed."""
    from world_cup_bot import ws_user
    from world_cup_bot.logic_version import load_strategy_version
    from world_cup_bot.operating_config import load_operating_config
    from world_cup_bot.reconcile import ReconcileState, run_reconcile_pass
    from world_cup_bot.scanner import discover_advance_markets

    auth = load_clob_auth()
    poly_address = load_poly_address()
    maker_address = load_maker_address()
    version_spec = load_strategy_version(Path(settings.logic_version_config))
    operating = load_operating_config(Path(settings.operating_config))
    markets = discover_advance_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
        operating=operating,
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={m.condition_id: m for m in markets},
        markets=markets,
        operating=operating,
        version_spec=version_spec,
        ledger_path=settings.ledger_path,
        dry_run=settings.dry_run,
        record=True,
        settings=settings,
        clob_url=settings.clob_url,
        auth=auth,
        poly_address=poly_address,
        maker_address=maker_address,
        reconcile_state=ReconcileState(),
    )
    ctx.reconcile_state.last_after_ts = int(
        (datetime.now(UTC) - timedelta(days=after_days)).timestamp()
    )
    stats = run_reconcile_pass(
        clob_url=settings.clob_url,
        auth=auth,
        poly_address=poly_address,
        maker_address=maker_address,
        ctx=ctx,
        state=ctx.reconcile_state,
    )
    return {
        "trades_fetched": stats.trades_fetched,
        "fills_processed": stats.fills_processed,
        "fills_skipped": stats.fills_skipped,
        "ledger_path": settings.ledger_path,
    }


def load_venue_order_ids(csv_path: Path) -> tuple[tuple[str, ...], str | None]:
    """Return order ids from Polymarket activity/trades CSV export."""
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        col = _find_order_id_column(reader.fieldnames)
        if not col:
            raise ValueError(
                "CSV missing order id column — expected one of: " + ", ".join(ORDER_ID_HEADERS)
            )
        ids: list[str] = []
        for row in reader:
            raw = (row.get(col) or "").strip()
            if raw:
                ids.append(raw)
    return tuple(ids), col


def compare_venue_csv(
    csv_path: Path,
    ledger_path: Path,
    *,
    logic_version: str | None = None,
) -> VenueReconcileReport:
    """Compare venue export order ids to ledger `order_fill` rows."""
    venue_ids = set(load_venue_order_ids(csv_path)[0])
    ledger_ids = load_ledger_fill_order_ids(ledger_path, logic_version=logic_version)
    return compare_venue_sets(ledger_ids, venue_ids)


def csv_template_lines() -> list[str]:
    return [
        "order_id,team,side,price,size,timestamp",
        "0xabc123...,USA,YES,0.42,100,2026-06-01T12:00:00Z",
    ]
