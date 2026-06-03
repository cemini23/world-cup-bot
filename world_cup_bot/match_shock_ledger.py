"""Dedicated JSONL ledger for Module 8 match-shock events."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot.ledger import load_rows
from world_cup_bot.match_shock import (
    EVENT_LADDER_PLANNED,
    EVENT_PAPER_FILL,
    EVENT_SHOCK_DETECTED,
    MATCH_SHOCK_SPEC,
    LadderOrder,
    LadderPlan,
    ShockDetection,
    ladder_plan_to_dict,
)
from world_cup_bot.match_shock_config import MatchShockConfig


@dataclass
class MatchShockLedgerRow:
    event: str
    logic_version: str
    strategy_key: str
    timestamp: str
    slug: str
    bucket_key: str | None = None
    pre_price: float | None = None
    depth_cents: float | None = None
    order_id: str | None = None
    pnl_usd: float | None = None
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


def _append(path: Path | str, row: MatchShockLedgerRow) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row.to_dict(), separators=(",", ":")) + "\n")


def default_ledger_path(cfg: MatchShockConfig, base: Path | str | None = None) -> Path:
    root = Path(base or "data/local")
    return root / cfg.paper_ledger_suffix


def record_shock_detected(
    path: Path | str,
    *,
    slug: str,
    detection: ShockDetection,
    bucket_key: str | None = None,
    depth_cents: float | None = None,
) -> None:
    _append(
        path,
        MatchShockLedgerRow(
            event=EVENT_SHOCK_DETECTED,
            logic_version=MATCH_SHOCK_SPEC.version_id,
            strategy_key=MATCH_SHOCK_SPEC.strategy_key,
            timestamp=_now_iso(),
            slug=slug,
            bucket_key=bucket_key,
            pre_price=detection.pre_price,
            depth_cents=depth_cents,
            extra={
                "peak": detection.peak,
                "floor": detection.floor,
                "depth": detection.depth,
            },
        ),
    )


def record_ladder_planned(
    path: Path | str,
    *,
    slug: str,
    plan: LadderPlan,
) -> None:
    _append(
        path,
        MatchShockLedgerRow(
            event=EVENT_LADDER_PLANNED,
            logic_version=MATCH_SHOCK_SPEC.version_id,
            strategy_key=MATCH_SHOCK_SPEC.strategy_key,
            timestamp=_now_iso(),
            slug=slug,
            bucket_key=plan.bucket_key,
            pre_price=plan.pre_price,
            extra={"plan": ladder_plan_to_dict(plan)},
        ),
    )


def record_paper_fill(
    path: Path | str,
    *,
    slug: str,
    plan: LadderPlan,
    fill: LadderOrder,
    pnl_usd: float | None = None,
) -> None:
    _append(
        path,
        MatchShockLedgerRow(
            event=EVENT_PAPER_FILL,
            logic_version=MATCH_SHOCK_SPEC.version_id,
            strategy_key=MATCH_SHOCK_SPEC.strategy_key,
            timestamp=_now_iso(),
            slug=slug,
            bucket_key=plan.bucket_key,
            pre_price=plan.pre_price,
            pnl_usd=pnl_usd,
            extra={
                "percentile": fill.percentile,
                "limit_price": fill.limit_price,
                "size_usd": fill.size_usd,
            },
        ),
    )


def record_live_post(
    path: Path | str,
    *,
    slug: str,
    plan: LadderPlan,
    order_id: str,
    limit_price: float,
    size_usd: float,
    percentile: int,
) -> None:
    _append(
        path,
        MatchShockLedgerRow(
            event="match_shock_live_post",
            logic_version=MATCH_SHOCK_SPEC.version_id,
            strategy_key=MATCH_SHOCK_SPEC.strategy_key,
            timestamp=_now_iso(),
            slug=slug,
            bucket_key=plan.bucket_key,
            pre_price=plan.pre_price,
            order_id=order_id,
            extra={
                "limit_price": limit_price,
                "size_usd": size_usd,
                "percentile": percentile,
            },
        ),
    )


def load_shock_rows(path: Path | str) -> list[dict[str, Any]]:
    return load_rows(path)


def recent_events(path: Path | str, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = load_shock_rows(path)
    return rows[-limit:]
