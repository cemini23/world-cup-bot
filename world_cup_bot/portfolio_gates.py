"""Multi-layer portfolio PnL gates — pause quoting on drawdown (K102)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from world_cup_bot.ledger import LedgerRow, append_row, load_rows
from world_cup_bot.logic_version import PnlScope, StrategyVersionSpec, filter_rows_by_scope
from world_cup_bot.risk_gates_config import RiskGatesConfig

if TYPE_CHECKING:
    from world_cup_bot.config import Settings


@dataclass(frozen=True)
class BankrollResolution:
    total_usd: float
    source: str
    free_usdc: float | None = None
    open_orders_usdc: float | None = None


@dataclass(frozen=True)
class PortfolioGateStatus:
    bankroll_usd: float | None
    cumulative_net_pnl_usd: float
    peak_equity_usd: float
    drawdown_pct: float
    daily_loss_usd: float
    monthly_loss_usd: float
    permanent_halt: bool
    active_pause: GateCheckResult | None
    bankroll_source: str | None = None
    bankroll_free_usdc: float | None = None
    bankroll_open_orders_usdc: float | None = None


def bankroll_usd_from_env() -> float | None:
    raw = os.environ.get("WC_BANKROLL_USD", "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    return val if val > 0 else None


def _bankroll_from_wallet_enabled() -> bool:
    raw = os.environ.get("WC_BANKROLL_FROM_WALLET", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return bankroll_usd_from_env() is None


def resolve_bankroll_usd(settings: Settings | None = None) -> BankrollResolution | None:
    """Bankroll for % gates: WC_BANKROLL_USD override, else live PM wallet when enabled."""
    static = bankroll_usd_from_env()
    if static is not None:
        return BankrollResolution(total_usd=static, source="env")

    if not _bankroll_from_wallet_enabled() or settings is None or settings.dry_run:
        return None

    from world_cup_bot.balance_cap import fetch_account_bankroll_usd, fetch_collateral_balance_usd

    try:
        total = fetch_account_bankroll_usd(settings)
        free = fetch_collateral_balance_usd(settings)
    except Exception:
        return None
    if total <= 0:
        return None
    locked = max(0.0, round(total - free, 2))
    return BankrollResolution(
        total_usd=total,
        source="wallet",
        free_usdc=round(free, 2),
        open_orders_usdc=locked,
    )


@dataclass(frozen=True)
class GateCheckResult:
    allowed: bool
    reason: str
    gate: str | None = None
    permanent_halt: bool = False
    paused_until: datetime | None = None


def _row_day(row: dict[str, Any]) -> str | None:
    ts = str(row.get("timestamp") or "")
    return ts[:10] if len(ts) >= 10 else None


def _row_month(row: dict[str, Any]) -> str | None:
    day = _row_day(row)
    return day[:7] if day else None


def _net_pnl_row(row: dict[str, Any]) -> float:
    from world_cup_bot.ledger import is_synthetic_backfill_exit

    if is_synthetic_backfill_exit(row):
        return 0.0
    if row.get("event") in {"order_fill", "exit_fill", "position_exit"}:
        for key in ("pnl_usd", "realized_pnl_usd"):
            val = row.get(key)
            if val is not None:
                return float(val)
    if row.get("event") in {"rewards_sync", "reward_accrual"}:
        return float(row.get("rewards_usd") or row.get("notional_usd") or 0)
    return 0.0


def cumulative_net_pnl(rows: list[dict[str, Any]], spec: StrategyVersionSpec) -> float:
    from world_cup_bot.ledger import summarize_pnl

    return summarize_pnl(rows, spec, PnlScope.CURRENT).net_pnl_usd


def peak_cumulative_pnl(rows: list[dict[str, Any]], spec: StrategyVersionSpec) -> float:
    """High-water cumulative net PnL (for drawdown vs bankroll)."""
    scoped = filter_rows_by_scope(rows, spec, PnlScope.CURRENT)
    dated: list[tuple[str, float]] = []
    for row in scoped:
        if row.get("event") not in {
            "order_fill",
            "exit_fill",
            "position_exit",
            "rewards_sync",
            "reward_accrual",
        }:
            continue
        ts = str(row.get("timestamp") or "")
        if row.get("event") in {"order_fill", "exit_fill", "position_exit"}:
            delta = _net_pnl_row(row)
            if row.get("fees_usd") is not None:
                delta -= float(row["fees_usd"])
        else:
            delta = float(row.get("rewards_usd") or 0)
        dated.append((ts, delta))
    dated.sort(key=lambda x: x[0])
    equity = 0.0
    peak = 0.0
    for _, delta in dated:
        equity += delta
        peak = max(peak, equity)
    return round(peak, 2)


def peak_equity_usd(
    rows: list[dict[str, Any]],
    spec: StrategyVersionSpec,
    *,
    bankroll_usd: float,
) -> float:
    return bankroll_usd + peak_cumulative_pnl(rows, spec)


def period_realized_loss_usd(
    rows: list[dict[str, Any]],
    spec: StrategyVersionSpec,
    *,
    day: str | None = None,
    month: str | None = None,
) -> float:
    scoped = filter_rows_by_scope(rows, spec, PnlScope.CURRENT)
    loss = 0.0
    for row in scoped:
        if row.get("event") not in {"order_fill", "exit_fill", "position_exit"}:
            continue
        if day and _row_day(row) != day:
            continue
        if month and _row_month(row) != month:
            continue
        pnl = _net_pnl_row(row)
        if pnl < 0:
            loss += abs(pnl)
    return round(loss, 2)


def _parse_until(row: dict[str, Any]) -> datetime | None:
    raw = row.get("paused_until") or (row.get("extra") or {}).get("paused_until")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def active_gate_pause(
    rows: list[dict[str, Any]],
    rg_cfg: RiskGatesConfig,
) -> GateCheckResult | None:
    now = datetime.now(UTC)
    permanent = any(r.get("event") == "risk_permanent_halt" for r in rows)
    if permanent:
        return GateCheckResult(
            allowed=False,
            reason="permanent halt active — operator reset required",
            gate="total_loss",
            permanent_halt=True,
        )
    for row in reversed(rows):
        if row.get("event") != "risk_gate_breach":
            continue
        if row.get("logic_version") != rg_cfg.logic_version:
            continue
        until = _parse_until(row)
        gate = str(row.get("gate") or row.get("reason") or "unknown")
        if until and until > now:
            return GateCheckResult(
                allowed=False,
                reason=f"{gate} pause until {until.isoformat()}",
                gate=gate,
                paused_until=until,
            )
    return None


def record_gate_breach(
    path: Path,
    rg_cfg: RiskGatesConfig,
    *,
    gate: str,
    reason: str,
    paused_until: datetime | None = None,
    permanent: bool = False,
) -> None:
    if permanent:
        append_row(
            path,
            LedgerRow(
                event="risk_permanent_halt",
                logic_version=rg_cfg.logic_version,
                strategy_key="pm_wc_risk_gates",
                timestamp=datetime.now(UTC).isoformat(),
                reason=reason,
                extra={"gate": gate},
            ),
        )
        return
    append_row(
        path,
        LedgerRow(
            event="risk_gate_breach",
            logic_version=rg_cfg.logic_version,
            strategy_key="pm_wc_risk_gates",
            timestamp=datetime.now(UTC).isoformat(),
            reason=reason,
            extra={
                "gate": gate,
                "paused_until": paused_until.isoformat() if paused_until else None,
            },
        ),
    )


def check_portfolio_gates(
    ledger_path: Path,
    spec: StrategyVersionSpec,
    rg_cfg: RiskGatesConfig,
    *,
    settings: Settings | None = None,
    record_breach: bool = False,
) -> GateCheckResult:
    pg = rg_cfg.portfolio_gates
    if not pg.enabled:
        return GateCheckResult(True, "portfolio gates disabled")

    resolved = resolve_bankroll_usd(settings)
    if resolved is None:
        if settings and settings.dry_run:
            return GateCheckResult(
                True,
                "portfolio gates deferred in DRY_RUN (live PM wallet bankroll on go-live)",
            )
        return GateCheckResult(
            False,
            "portfolio gates enabled but bankroll unavailable "
            "(set WC_BANKROLL_USD or live WC_BANKROLL_FROM_WALLET with L2 creds)",
            gate="config",
        )
    bankroll = resolved.total_usd
    bankroll_note = (
        f"wallet ${resolved.free_usdc:.2f} free + ${resolved.open_orders_usdc:.2f} orders"
        if resolved.source == "wallet"
        and resolved.free_usdc is not None
        and resolved.open_orders_usdc is not None
        else f"bankroll ${bankroll:.2f}"
    )

    if not ledger_path.is_file():
        return GateCheckResult(True, f"portfolio gates OK (no ledger; {bankroll_note})")

    rows = load_rows(ledger_path)
    pause = active_gate_pause(rows, rg_cfg)
    if pause and not pause.allowed:
        return pause

    now = datetime.now(UTC)
    day = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")

    cum = cumulative_net_pnl(rows, spec)
    equity = bankroll + cum
    peak = bankroll + max(peak_cumulative_pnl(rows, spec), cum)
    drawdown = (peak - equity) / peak if peak > 0 else 0.0

    daily_loss = period_realized_loss_usd(rows, spec, day=day)
    monthly_loss = period_realized_loss_usd(rows, spec, month=month)
    total_loss = max(0.0, -cum)

    checks: list[tuple[str, bool, str, timedelta | None, bool]] = [
        (
            "total_loss",
            total_loss / bankroll >= pg.total_loss_pct,
            f"total loss ${total_loss:.2f} >= {pg.total_loss_pct:.0%} of bankroll",
            None,
            True,
        ),
        (
            "peak_drawdown",
            drawdown >= pg.peak_drawdown_pct,
            f"drawdown {drawdown:.1%} >= {pg.peak_drawdown_pct:.0%}",
            timedelta(days=pg.peak_pause_days),
            False,
        ),
        (
            "monthly_loss",
            monthly_loss / bankroll >= pg.monthly_loss_pct,
            f"monthly loss ${monthly_loss:.2f} >= {pg.monthly_loss_pct:.0%} of bankroll",
            timedelta(days=pg.monthly_pause_days),
            False,
        ),
        (
            "daily_loss",
            daily_loss / bankroll >= pg.daily_loss_pct,
            f"daily loss ${daily_loss:.2f} >= {pg.daily_loss_pct:.0%} of bankroll",
            timedelta(minutes=pg.daily_pause_minutes),
            False,
        ),
    ]

    for gate, triggered, detail, pause_delta, permanent in checks:
        if not triggered:
            continue
        until = None if permanent else now + (pause_delta or timedelta(0))
        if record_breach:
            record_gate_breach(
                ledger_path,
                rg_cfg,
                gate=gate,
                reason=detail,
                paused_until=until,
                permanent=permanent,
            )
        return GateCheckResult(
            allowed=False,
            reason=detail,
            gate=gate,
            permanent_halt=permanent,
            paused_until=until,
        )

    return GateCheckResult(True, f"portfolio gates OK (equity ${equity:.2f} / peak ${peak:.2f})")


def portfolio_status(
    ledger_path: Path,
    spec: StrategyVersionSpec,
    rg_cfg: RiskGatesConfig,
    *,
    settings: Settings | None = None,
) -> PortfolioGateStatus:
    resolved = resolve_bankroll_usd(settings)
    bankroll = resolved.total_usd if resolved else None
    rows = load_rows(ledger_path) if ledger_path.is_file() else []
    now = datetime.now(UTC)
    cum = cumulative_net_pnl(rows, spec) if rows else 0.0
    peak = (bankroll or 0.0) + (peak_cumulative_pnl(rows, spec) if rows else max(cum, 0.0))
    equity = (bankroll or 0.0) + cum
    drawdown = (peak - equity) / peak if peak > 0 else 0.0
    pause = active_gate_pause(rows, rg_cfg) if rows else None
    permanent = bool(pause and pause.permanent_halt)
    return PortfolioGateStatus(
        bankroll_usd=bankroll,
        cumulative_net_pnl_usd=cum,
        peak_equity_usd=round(peak, 2),
        drawdown_pct=round(drawdown, 4),
        daily_loss_usd=period_realized_loss_usd(rows, spec, day=now.strftime("%Y-%m-%d"))
        if rows
        else 0.0,
        monthly_loss_usd=period_realized_loss_usd(rows, spec, month=now.strftime("%Y-%m"))
        if rows
        else 0.0,
        permanent_halt=permanent,
        active_pause=pause,
        bankroll_source=resolved.source if resolved else None,
        bankroll_free_usdc=resolved.free_usdc if resolved else None,
        bankroll_open_orders_usdc=resolved.open_orders_usdc if resolved else None,
    )
