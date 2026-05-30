"""Phase B — manual cross-venue fill bridge + CSV import + reconcile."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot.cross_venue_paper import (
    PAPER_ARB_SPEC,
    _latest_intents_by_pair,
    _leg_direction,
    _pair_key,
)
from world_cup_bot.ledger import LedgerRow, append_row

EVENT_FILL = "cross_venue_arb_fill_manual"

CSV_COMBINED_FIELDS = (
    "timestamp",
    "team",
    "market_type",
    "pm_leg",
    "kalshi_leg",
    "pm_price",
    "kalshi_price",
    "notional_usd",
    "fees_usd",
    "order_id_pm",
    "order_id_kalshi",
    "notes",
)


@dataclass(frozen=True)
class ManualFillInput:
    team: str
    market_type: str
    pm_fill_price: float
    kalshi_fill_price: float
    notional_usd: float
    pm_leg: str | None = None
    kalshi_leg: str | None = None
    fees_usd: float = 0.0
    notes: str | None = None
    correlation_id: str | None = None
    order_id_pm: str | None = None
    order_id_kalshi: str | None = None
    source: str = "cli"


@dataclass(frozen=True)
class ManualFillResult:
    intent_key: str
    realized_pnl_usd: float
    pm_leg: str
    kalshi_leg: str


@dataclass(frozen=True)
class CsvImportResult:
    imported: int
    skipped: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ReconcileRow:
    intent_key: str
    team: str
    market_type: str
    has_intent: bool
    has_fill: bool
    entry_profit_usd: float | None
    realized_pnl_usd: float | None
    delta_usd: float | None
    status: str  # matched | intent_only | fill_only

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_key": self.intent_key,
            "team": self.team,
            "market_type": self.market_type,
            "has_intent": self.has_intent,
            "has_fill": self.has_fill,
            "entry_profit_usd": self.entry_profit_usd,
            "realized_pnl_usd": self.realized_pnl_usd,
            "delta_usd": self.delta_usd,
            "status": self.status,
        }


@dataclass(frozen=True)
class ReconcileReport:
    logic_version: str
    intent_pairs: int
    fill_pairs: int
    matched: int
    intent_only: int
    fill_only: int
    total_entry_profit_usd: float
    total_realized_pnl_usd: float
    rows: tuple[ReconcileRow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "logic_version": self.logic_version,
            "intent_pairs": self.intent_pairs,
            "fill_pairs": self.fill_pairs,
            "matched": self.matched,
            "intent_only": self.intent_only,
            "fill_only": self.fill_only,
            "total_entry_profit_usd": self.total_entry_profit_usd,
            "total_realized_pnl_usd": self.total_realized_pnl_usd,
            "rows": [r.to_dict() for r in self.rows],
        }


def compute_realized_pnl_usd(
    pm_leg: str,
    kalshi_leg: str,
    pm_price: float,
    kalshi_price: float,
    notional_usd: float,
    fees_usd: float = 0.0,
) -> float:
    """Gross spread capture minus fees (prices on 0–1 YES scale)."""
    pm_leg = pm_leg.upper()
    kalshi_leg = kalshi_leg.upper()
    if pm_leg == "SELL" and kalshi_leg == "BUY":
        gross = notional_usd * (pm_price - kalshi_price)
    elif pm_leg == "BUY" and kalshi_leg == "SELL":
        gross = notional_usd * (kalshi_price - pm_price)
    else:
        raise ValueError(f"Invalid arb legs: pm={pm_leg} kalshi={kalshi_leg}")
    return round(gross - fees_usd, 2)


def _resolve_legs(
    pm_price: float,
    kalshi_price: float,
    pm_leg: str | None,
    kalshi_leg: str | None,
) -> tuple[str, str]:
    if pm_leg and kalshi_leg:
        return pm_leg.upper(), kalshi_leg.upper()
    return _leg_direction(pm_price, kalshi_price)


def record_manual_fill(
    path: Path,
    fill: ManualFillInput,
    *,
    now: datetime | None = None,
) -> ManualFillResult:
    now = now or datetime.now(UTC)
    pm_leg, kal_leg = _resolve_legs(
        fill.pm_fill_price,
        fill.kalshi_fill_price,
        fill.pm_leg,
        fill.kalshi_leg,
    )
    intent_key = _pair_key(fill.team, fill.market_type)
    realized = compute_realized_pnl_usd(
        pm_leg,
        kal_leg,
        fill.pm_fill_price,
        fill.kalshi_fill_price,
        fill.notional_usd,
        fill.fees_usd,
    )

    append_row(
        path,
        LedgerRow(
            event=EVENT_FILL,
            logic_version=PAPER_ARB_SPEC.version_id,
            strategy_key=PAPER_ARB_SPEC.strategy_key,
            timestamp=now.isoformat(),
            team=fill.team,
            notional_usd=fill.notional_usd,
            pnl_usd=realized,
            fees_usd=fill.fees_usd or None,
            reason="manual_fill",
            correlation_id=fill.correlation_id,
            extra={
                "intent_key": intent_key,
                "market_type": fill.market_type,
                "pm_leg": pm_leg,
                "kalshi_leg": kal_leg,
                "pm_fill_price": fill.pm_fill_price,
                "kalshi_fill_price": fill.kalshi_fill_price,
                "realized_pnl_usd": realized,
                "source": fill.source,
                "notes": fill.notes,
                "order_id_pm": fill.order_id_pm,
                "order_id_kalshi": fill.order_id_kalshi,
            },
        ),
    )
    return ManualFillResult(
        intent_key=intent_key,
        realized_pnl_usd=realized,
        pm_leg=pm_leg,
        kalshi_leg=kal_leg,
    )


def _parse_float(raw: str | None, default: float = 0.0) -> float:
    if raw is None or str(raw).strip() == "":
        return default
    return float(raw)


def _parse_row_timestamp(raw: str | None, fallback: datetime) -> datetime:
    if not raw or not str(raw).strip():
        return fallback
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _fill_from_csv_row(row: dict[str, str], *, row_num: int) -> ManualFillInput:
    team = (row.get("team") or "").strip()
    market_type = (row.get("market_type") or "").strip()
    if not team or not market_type:
        raise ValueError(f"row {row_num}: team and market_type required")

    pm_price = _parse_float(row.get("pm_price"))
    kal_price = _parse_float(row.get("kalshi_price"))
    if pm_price <= 0 or kal_price <= 0:
        raise ValueError(f"row {row_num}: pm_price and kalshi_price required")

    return ManualFillInput(
        team=team,
        market_type=market_type,
        pm_fill_price=pm_price,
        kalshi_fill_price=kal_price,
        notional_usd=_parse_float(row.get("notional_usd"), 500.0),
        pm_leg=(row.get("pm_leg") or "").strip() or None,
        kalshi_leg=(row.get("kalshi_leg") or "").strip() or None,
        fees_usd=_parse_float(row.get("fees_usd")),
        notes=(row.get("notes") or "").strip() or None,
        order_id_pm=(row.get("order_id_pm") or "").strip() or None,
        order_id_kalshi=(row.get("order_id_kalshi") or "").strip() or None,
        source="csv",
    )


def import_fills_csv(
    path: Path,
    csv_path: Path,
    *,
    dry_run: bool = False,
) -> CsvImportResult:
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)

    imported = 0
    skipped = 0
    errors: list[str] = []
    now = datetime.now(UTC)

    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return CsvImportResult(0, 0, ("empty csv",))
        fields = {f.strip().lower() for f in reader.fieldnames}
        if "pm_price" not in fields or "kalshi_price" not in fields:
            return CsvImportResult(
                0,
                0,
                (
                    "CSV must include pm_price,kalshi_price columns "
                    f"(got {reader.fieldnames})",
                ),
            )

        for idx, raw_row in enumerate(reader, start=2):
            row = {k.strip().lower(): (v or "") for k, v in raw_row.items() if k}
            if not any(str(v).strip() for v in row.values()):
                skipped += 1
                continue
            try:
                fill = _fill_from_csv_row(row, row_num=idx)
                ts = _parse_row_timestamp(row.get("timestamp"), now)
                if dry_run:
                    imported += 1
                    continue
                record_manual_fill(path, fill, now=ts)
                imported += 1
            except (ValueError, KeyError) as exc:
                errors.append(str(exc))

    return CsvImportResult(imported=imported, skipped=skipped, errors=tuple(errors))


def _latest_fills_by_pair(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("event") != EVENT_FILL:
            continue
        key = str(
            row.get("intent_key")
            or _pair_key(str(row.get("team")), str(row.get("market_type")))
        )
        prev = out.get(key)
        if prev is None or str(row.get("timestamp", "")) > str(prev.get("timestamp", "")):
            out[key] = row
    return out


def build_reconcile_report(rows: list[dict[str, Any]]) -> ReconcileReport:
    intents = _latest_intents_by_pair(rows)
    fills = _latest_fills_by_pair(rows)
    all_keys = sorted(set(intents) | set(fills))

    report_rows: list[ReconcileRow] = []
    matched = intent_only = fill_only = 0
    entry_total = 0.0
    realized_total = 0.0

    for key in all_keys:
        intent = intents.get(key)
        fill = fills.get(key)
        has_intent = intent is not None
        has_fill = fill is not None

        entry_profit: float | None = None
        realized: float | None = None
        delta: float | None = None
        team = ""
        market_type = ""

        if intent is not None:
            team = str(intent.get("team") or key.split(":", 1)[-1])
            market_type = str(intent.get("market_type") or key.split(":", 1)[0])
            entry_profit = float(
                intent.get("theoretical_profit_usd") or intent.get("pnl_usd") or 0
            )
            entry_total += entry_profit

        if fill is not None:
            if not team:
                team = str(fill.get("team") or "")
            if not market_type:
                market_type = str(fill.get("market_type") or key.split(":", 1)[0])
            realized = float(fill.get("realized_pnl_usd") or fill.get("pnl_usd") or 0)
            realized_total += realized

        if has_intent and has_fill:
            status = "matched"
            matched += 1
            if entry_profit is not None and realized is not None:
                delta = round(realized - entry_profit, 2)
        elif has_intent:
            status = "intent_only"
            intent_only += 1
        else:
            status = "fill_only"
            fill_only += 1

        report_rows.append(
            ReconcileRow(
                intent_key=key,
                team=team,
                market_type=market_type,
                has_intent=has_intent,
                has_fill=has_fill,
                entry_profit_usd=entry_profit,
                realized_pnl_usd=realized,
                delta_usd=delta,
                status=status,
            )
        )

    return ReconcileReport(
        logic_version=PAPER_ARB_SPEC.version_id,
        intent_pairs=len(intents),
        fill_pairs=len(fills),
        matched=matched,
        intent_only=intent_only,
        fill_only=fill_only,
        total_entry_profit_usd=round(entry_total, 2),
        total_realized_pnl_usd=round(realized_total, 2),
        rows=tuple(report_rows),
    )


def csv_template_lines() -> Iterable[str]:
    yield ",".join(CSV_COMBINED_FIELDS)
    yield (
        "2026-05-30T12:00:00Z,USA,group_winner,SELL,BUY,0.68,0.64,500,2.10,,,"
        "manual both legs after alert"
    )
