"""Venue CSV vs bot ledger reconcile — blind-spot #2 (Gustafssonkotte rule)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from world_cup_bot.ledger import load_rows

ORDER_ID_HEADERS = (
    "order_id",
    "order id",
    "orderid",
    "id",
    "trade_id",
    "trade id",
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


def load_venue_order_ids(csv_path: Path) -> tuple[tuple[str, ...], str | None]:
    """Return order ids from Polymarket activity/trades CSV export."""
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        col = _find_order_id_column(reader.fieldnames)
        if not col:
            raise ValueError(
                "CSV missing order id column — expected one of: "
                + ", ".join(ORDER_ID_HEADERS)
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
    rows = load_rows(ledger_path)
    ledger_ids = {
        str(r["order_id"])
        for r in rows
        if r.get("event") == "order_fill"
        and r.get("order_id")
        and (logic_version is None or r.get("logic_version") == logic_version)
    }
    matched = ledger_ids & venue_ids
    return VenueReconcileReport(
        ledger_fill_count=len(ledger_ids),
        venue_row_count=len(venue_ids),
        matched=len(matched),
        ledger_only=tuple(sorted(ledger_ids - venue_ids)),
        venue_only=tuple(sorted(venue_ids - ledger_ids)),
    )


def csv_template_lines() -> list[str]:
    return [
        "order_id,team,side,price,size,timestamp",
        "0xabc123...,USA,YES,0.42,100,2026-06-01T12:00:00Z",
    ]
