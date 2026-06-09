"""Round-trip fill economics — entry/exit PnL attribution (Module 4 + 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from world_cup_bot.fill_handler import ExitIntent
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.operating_config import OperatingConfig


def compute_exit_pnl_usd(*, entry_price: float, exit_price: float, size_shares: float) -> float:
    """Maker BUY entry + limit SELL exit on same outcome token."""
    return round((exit_price - entry_price) * size_shares, 4)


def position_exit_exists(rows: list[dict[str, Any]], entry_order_id: str) -> bool:
    for row in rows:
        if row.get("event") != "position_exit":
            continue
        extra = row.get("extra") or {}
        entry_id = (
            extra.get("entry_order_id") or row.get("entry_order_id") or row.get("correlation_id")
        )
        if entry_id == entry_order_id:
            return True
    return False


def find_entry_fill(rows: list[dict[str, Any]], entry_order_id: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("event") == "order_fill" and row.get("order_id") == entry_order_id:
            return row
    return None


def attribute_roundtrip_from_exit_intent(
    *,
    path: Path,
    spec: StrategyVersionSpec,
    exit_intent: ExitIntent,
    fill_order_id: str,
    entry_price: float,
    dry_run: bool,
) -> float | None:
    """Write position_exit row for entry↔exit intent pair; return pnl_usd."""
    from world_cup_bot.ledger import load_rows, record_position_exit

    rows = load_rows(path) if path.is_file() else []
    if position_exit_exists(rows, fill_order_id):
        return None

    pnl = compute_exit_pnl_usd(
        entry_price=entry_price,
        exit_price=exit_intent.price,
        size_shares=exit_intent.size_shares,
    )
    record_position_exit(
        path=path,
        spec=spec,
        team=exit_intent.team,
        side=exit_intent.side,
        entry_order_id=fill_order_id,
        exit_order_id=exit_intent.order_id,
        entry_price=entry_price,
        exit_price=exit_intent.price,
        size_shares=exit_intent.size_shares,
        pnl_usd=pnl,
        dry_run=dry_run,
        reason=exit_intent.reason,
        kill_switch=exit_intent.kill_switch,
    )
    return pnl


def backfill_position_exits(path: Path, spec: StrategyVersionSpec) -> int:
    """Attribute PnL for historical exit_intent rows missing position_exit."""
    from world_cup_bot.ledger import load_rows

    if not path.is_file():
        return 0
    rows = load_rows(path)
    written = 0
    for row in rows:
        if row.get("event") not in ("exit_intent", "exit_intent_dry_run"):
            continue
        extra = row.get("extra") or {}
        fill_order_id = row.get("fill_order_id") or extra.get("fill_order_id")
        if not fill_order_id:
            continue
        if position_exit_exists(rows, fill_order_id):
            continue
        entry = find_entry_fill(rows, fill_order_id)
        if entry is None:
            continue
        entry_price = float(entry.get("price") or 0)
        size = float(
            entry.get("size_shares") or row.get("size_shares") or extra.get("size_shares") or 0
        )
        if entry_price <= 0 or size <= 0:
            continue
        exit_price = float(row.get("price") or 0)
        dry = row.get("event") == "exit_intent_dry_run"
        from datetime import datetime

        from world_cup_bot.fill_handler import ExitIntent

        due_raw = row.get("due_by") or extra.get("due_by")
        due_by = (
            datetime.fromisoformat(str(due_raw).replace("Z", "+00:00"))
            if due_raw
            else datetime.now().astimezone()
        )
        intent = ExitIntent(
            team=str(row.get("team") or entry.get("team") or ""),
            side=row.get("side") or entry.get("side") or "YES",  # type: ignore[arg-type]
            token_id=str(row.get("token_id") or extra.get("token_id") or ""),
            order_id=str(row.get("order_id") or ""),
            price=exit_price,
            size_shares=size,
            due_by=due_by,
            reason=str(row.get("reason") or "backfill"),
            kill_switch=bool(
                row.get("kill_switch")
                if row.get("kill_switch") is not None
                else extra.get("kill_switch")
            ),
        )
        if (
            attribute_roundtrip_from_exit_intent(
                path=path,
                spec=spec,
                exit_intent=intent,
                fill_order_id=fill_order_id,
                entry_price=entry_price,
                dry_run=dry,
            )
            is not None
        ):
            written += 1
            rows = load_rows(path)
    return written


def synthesize_position_exits_from_entry_fills(
    path: Path,
    spec: StrategyVersionSpec,
    operating: OperatingConfig,
) -> int:
    """Attribute synthetic round-trip PnL for entry fills missing exit_intent rows."""
    from world_cup_bot.fill_handler import build_exit_price
    from world_cup_bot.ledger import load_rows, record_position_exit

    if not path.is_file():
        return 0
    ops = operating.fill_handler
    rows = load_rows(path)
    written = 0
    for row in rows:
        if row.get("event") != "order_fill":
            continue
        entry_order_id = str(row.get("order_id") or "")
        if not entry_order_id or position_exit_exists(rows, entry_order_id):
            continue
        entry_price = float(row.get("price") or 0)
        size = float(row.get("size_shares") or 0)
        if entry_price <= 0 or size <= 0:
            continue
        exit_price = build_exit_price(entry_price, ops)
        pnl = compute_exit_pnl_usd(
            entry_price=entry_price,
            exit_price=exit_price,
            size_shares=size,
        )
        record_position_exit(
            path=path,
            spec=spec,
            team=str(row.get("team") or ""),
            side=str(row.get("side") or "YES"),
            entry_order_id=entry_order_id,
            exit_order_id=f"backfill-synthetic-{entry_order_id[-12:]}",
            entry_price=entry_price,
            exit_price=exit_price,
            size_shares=size,
            pnl_usd=pnl,
            dry_run=True,
            reason="backfill_synthetic_exit",
        )
        written += 1
        rows = load_rows(path)
    return written
