"""Daily P&L ledger — append-only JSONL with logic_version on every row (Module 7)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot.fill_handler import ExitIntent
from world_cup_bot.logic_version import (
    LEGACY_UNVERSIONED,
    PnlScope,
    StrategyVersionSpec,
    filter_rows_by_scope,
)
from world_cup_bot.quoter import MarketSnapshot, QuoteIntent

DEFAULT_LEDGER = Path("data/local/ledger.jsonl")


class DuplicateFillError(Exception):
    """Raised when the same order_id is recorded twice (blind-spot #4)."""


@dataclass
class LedgerRow:
    """Structured ledger event — stable fields for grep/Loki-style queries."""

    event: str
    logic_version: str
    strategy_key: str
    timestamp: str
    team: str | None = None
    side: str | None = None
    order_id: str | None = None
    price: float | None = None
    size_shares: float | None = None
    notional_usd: float | None = None
    pnl_usd: float | None = None
    rewards_usd: float | None = None
    fees_usd: float | None = None
    reason: str | None = None
    correlation_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        base = asdict(self)
        extra = base.pop("extra") or {}
        out = {k: v for k, v in base.items() if v is not None}
        if extra:
            out.update(extra)
        return out


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _snapshot_fields(snapshot: MarketSnapshot) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "mid_at_place": snapshot.mid,
        "rewards_min_shares": snapshot.rewards_min_shares,
        "rewards_max_spread": snapshot.rewards_max_spread,
    }
    if snapshot.best_bid is not None:
        fields["best_bid_at_place"] = snapshot.best_bid
    if snapshot.best_ask is not None:
        fields["best_ask_at_place"] = snapshot.best_ask
    if snapshot.spread is not None:
        fields["spread_at_place"] = snapshot.spread
    if snapshot.hours_to_kickoff is not None:
        fields["hours_to_kickoff"] = snapshot.hours_to_kickoff
    return fields


def _as_path(path: Path | str) -> Path:
    return path if isinstance(path, Path) else Path(path)


def fill_order_ids(path: Path | str) -> set[str]:
    return {
        str(r["order_id"])
        for r in load_rows(path)
        if r.get("event") == "order_fill" and r.get("order_id")
    }


def reward_accrual_keys(path: Path) -> set[str]:
    return {
        str(r["reward_key"])
        for r in load_rows(path)
        if r.get("event") == "reward_accrual" and r.get("reward_key")
    }


def append_row(path: Path | str, row: LedgerRow) -> None:
    path = _as_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row.to_dict(), separators=(",", ":")) + "\n")


def load_rows(path: Path | str) -> list[dict[str, Any]]:
    path = _as_path(path)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def record_quote_intents(
    intents: list[QuoteIntent],
    spec: StrategyVersionSpec,
    *,
    path: Path,
    correlation_id: str | None = None,
    dry_run: bool = True,
    tournament_phase: str | None = None,
    market_phase_id: str | None = None,
) -> int:
    """Log quote intents as quote_intent events (DRY_RUN or live submit)."""
    event = "quote_intent_dry_run" if dry_run else "quote_intent"
    cid = correlation_id or f"plan-{_now_iso()}"
    for intent in intents:
        extra = {"token_id": intent.token_id, **_snapshot_fields(intent.snapshot)}
        if tournament_phase:
            extra["tournament_phase"] = tournament_phase
        if market_phase_id:
            extra["market_phase_id"] = market_phase_id
        append_row(
            path,
            LedgerRow(
                event=event,
                logic_version=spec.version_id,
                strategy_key=spec.strategy_key,
                timestamp=_now_iso(),
                team=intent.team,
                side=intent.side,
                order_id=intent.order_id,
                price=intent.price,
                size_shares=intent.size_shares,
                notional_usd=intent.notional_usd,
                reason=intent.reason,
                correlation_id=cid,
                extra=extra,
            ),
        )
    return len(intents)


def record_fill(
    *,
    path: Path,
    spec: StrategyVersionSpec,
    team: str,
    side: str,
    order_id: str,
    price: float,
    size_shares: float,
    pnl_usd: float | None = None,
    fees_usd: float | None = None,
    reason: str | None = None,
    correlation_id: str | None = None,
    allow_duplicate: bool = False,
) -> bool:
    """Append fill row; return False if order_id already recorded (dedup)."""
    if not allow_duplicate and order_id in fill_order_ids(path):
        return False
    append_row(
        path,
        LedgerRow(
            event="order_fill",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=_now_iso(),
            team=team,
            side=side,
            order_id=order_id,
            price=price,
            size_shares=size_shares,
            notional_usd=price * size_shares,
            pnl_usd=pnl_usd,
            fees_usd=fees_usd,
            reason=reason,
            correlation_id=correlation_id,
        ),
    )
    return True


def record_exit_intent(
    intent: ExitIntent,
    spec: StrategyVersionSpec,
    *,
    path: Path,
    fill_order_id: str,
    correlation_id: str | None = None,
    dry_run: bool = True,
) -> None:
    event = "exit_intent_dry_run" if dry_run else "exit_intent"
    append_row(
        path,
        LedgerRow(
            event=event,
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=_now_iso(),
            team=intent.team,
            side=intent.side,
            order_id=intent.order_id,
            price=intent.price,
            size_shares=intent.size_shares,
            reason=intent.reason,
            correlation_id=correlation_id,
            extra={
                "token_id": intent.token_id,
                "fill_order_id": fill_order_id,
                "due_by": intent.due_by.isoformat(),
                "kill_switch": intent.kill_switch,
            },
        ),
    )


def record_order_cancel(
    spec: StrategyVersionSpec,
    *,
    path: Path,
    order_ids: list[str],
    reason: str,
    teams: tuple[str, ...] = (),
    dry_run: bool = True,
) -> None:
    """Append cancel batch for audit trail."""
    if not order_ids:
        return
    event = "order_cancel_dry_run" if dry_run else "order_cancel"
    append_row(
        path,
        LedgerRow(
            event=event,
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=_now_iso(),
            reason=reason,
            extra={
                "order_ids": order_ids,
                "order_count": len(order_ids),
                "teams": list(teams),
            },
        ),
    )


def record_reward_accrual(
    spec: StrategyVersionSpec,
    *,
    path: Path,
    team: str,
    rewards_usd: float,
    reward_key: str,
    earn_date: str,
    condition_id: str,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Append reward_accrual row; return False if reward_key already recorded."""
    if reward_key in reward_accrual_keys(path):
        return False
    payload = {
        "reward_key": reward_key,
        "earn_date": earn_date,
        "condition_id": condition_id,
    }
    if extra:
        payload.update(extra)
    append_row(
        path,
        LedgerRow(
            event="reward_accrual",
            logic_version=spec.version_id,
            strategy_key=spec.strategy_key,
            timestamp=_now_iso(),
            team=team,
            rewards_usd=rewards_usd,
            extra=payload,
        ),
    )
    return True


@dataclass(frozen=True)
class PnlSummary:
    logic_version: str
    strategy_key: str
    scope: str
    row_count: int
    quote_intents: int
    fills: int
    realized_pnl_usd: float
    rewards_usd: float
    fees_usd: float
    net_pnl_usd: float
    legacy_excluded: int


def summarize_pnl(
    rows: list[dict[str, Any]],
    spec: StrategyVersionSpec,
    scope: PnlScope,
) -> PnlSummary:
    total_before = len(rows)
    scoped = filter_rows_by_scope(rows, spec, scope)
    legacy_excluded = total_before - len(scoped) if scope == PnlScope.CURRENT else 0

    quote_intents = sum(
        1 for r in scoped if r.get("event") in {"quote_intent", "quote_intent_dry_run"}
    )
    fills = sum(1 for r in scoped if r.get("event") == "order_fill")

    realized = sum(float(r.get("pnl_usd") or 0) for r in scoped if r.get("event") == "order_fill")
    rewards = sum(float(r.get("rewards_usd") or 0) for r in scoped)
    fees = sum(float(r.get("fees_usd") or 0) for r in scoped)
    net = realized + rewards - fees

    version_label = spec.version_id if scope == PnlScope.CURRENT else f"{scope.value}_mix"

    return PnlSummary(
        logic_version=version_label,
        strategy_key=spec.strategy_key,
        scope=scope.value,
        row_count=len(scoped),
        quote_intents=quote_intents,
        fills=fills,
        realized_pnl_usd=round(realized, 2),
        rewards_usd=round(rewards, 2),
        fees_usd=round(fees, 2),
        net_pnl_usd=round(net, 2),
        legacy_excluded=legacy_excluded,
    )


def summarize_by_version(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grouped metrics for forensics (--scope all breakdown)."""
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        v = row.get("logic_version") or LEGACY_UNVERSIONED
        buckets.setdefault(str(v), []).append(row)

    out: list[dict[str, Any]] = []
    for version_id, group in sorted(buckets.items()):
        pseudo_spec = StrategyVersionSpec(
            strategy_key="pm_wc_advance_lp",
            version_id=version_id,
            deployed_at=datetime.now(UTC),
            note="",
            legacy_version_ids=frozenset(),
        )
        s = summarize_pnl(group, pseudo_spec, PnlScope.ALL)
        out.append(
            {
                "logic_version": version_id,
                "row_count": s.row_count,
                "fills": s.fills,
                "net_pnl_usd": s.net_pnl_usd,
            }
        )
    return out
