"""Event-scoped risk gates — daily adverse-fill budget (Cemini risk_manager pattern, adapted)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from world_cup_bot.ledger import load_rows
from world_cup_bot.logic_version import PnlScope, StrategyVersionSpec, filter_rows_by_scope
from world_cup_bot.operating_config import OperatingConfig


def _row_day(row: dict) -> str | None:
    ts = str(row.get("timestamp") or row.get("ts") or row.get("recorded_at") or "")
    return ts[:10] if len(ts) >= 10 else None


def daily_adverse_fill_usd(
    rows: list[dict],
    *,
    day: str | None = None,
    spec: StrategyVersionSpec | None = None,
) -> float:
    """Sum of |negative pnl_usd| on order_fill rows for UTC day (default today)."""
    target_day = day or datetime.now(UTC).strftime("%Y-%m-%d")
    scoped = filter_rows_by_scope(rows, spec, PnlScope.CURRENT) if spec else rows
    total = 0.0
    for row in scoped:
        if row.get("event") != "order_fill":
            continue
        if _row_day(row) != target_day:
            continue
        pnl = float(row.get("pnl_usd") or 0)
        if pnl < 0:
            total += abs(pnl)
    return round(total, 2)


def check_daily_adverse_budget(
    ledger_path: Path,
    operating: OperatingConfig,
    spec: StrategyVersionSpec,
    *,
    day: str | None = None,
) -> tuple[bool, str]:
    cap = operating.risk.max_daily_adverse_fill_usd
    if cap <= 0:
        return True, "daily adverse cap disabled (max_daily_adverse_fill_usd <= 0)"

    if not ledger_path.is_file():
        return True, f"daily adverse $0.00 / cap ${cap:.0f} (no ledger yet)"

    adverse = daily_adverse_fill_usd(load_rows(ledger_path), day=day, spec=spec)
    if adverse >= cap:
        return (
            False,
            f"daily adverse fill ${adverse:.2f} >= cap ${cap:.2f} — plan blocked",
        )
    return True, f"daily adverse ${adverse:.2f} / cap ${cap:.2f}"


def shadow_net_pnl_ok(
    ledger_path: Path,
    spec: StrategyVersionSpec,
    *,
    min_fills: int = 1,
) -> tuple[bool, str]:
    """LP promotion heuristic: net PnL >= 0 when fills exist (Phase-0 spec shadow floor)."""
    if not ledger_path.is_file():
        return False, "no ledger — run plan --record during shadow soak"

    from world_cup_bot.ledger import summarize_pnl

    rows = load_rows(ledger_path)
    summary = summarize_pnl(rows, spec, PnlScope.CURRENT)
    if summary.fills < min_fills:
        return True, f"shadow PnL n/a ({summary.fills} fills — need {min_fills}+ for gate)"

    if summary.net_pnl_usd >= 0:
        return True, f"shadow net PnL ${summary.net_pnl_usd:+.2f} (rewards + fills - fees)"
    return (
        False,
        f"shadow net PnL ${summary.net_pnl_usd:+.2f} < 0 — review before live pilot",
    )
