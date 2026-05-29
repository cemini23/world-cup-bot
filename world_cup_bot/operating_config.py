"""Load operating thresholds from YAML (wiki invariants — not live prices)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_OPERATING = Path(__file__).resolve().parent.parent / "config" / "operating.yaml"


@dataclass(frozen=True)
class CalendarOps:
    prefer_hours_before_kickoff: float


@dataclass(frozen=True)
class BilateralOps:
    high_mid: float
    low_mid: float


@dataclass(frozen=True)
class FillHandlerOps:
    exit_within_seconds: float
    queue_depletion_usd: float
    vol_drop_pct: float
    exit_loss_ticks: int


@dataclass(frozen=True)
class OperatingConfig:
    calendar: CalendarOps
    bilateral: BilateralOps
    fill_handler: FillHandlerOps


def load_operating_config(path: Path | None = None) -> OperatingConfig:
    p = path or DEFAULT_OPERATING
    with p.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    cal = raw.get("calendar") or {}
    bil = raw.get("bilateral") or {}
    fh = raw.get("fill_handler") or {}

    return OperatingConfig(
        calendar=CalendarOps(
            prefer_hours_before_kickoff=float(cal.get("prefer_hours_before_kickoff", 24)),
        ),
        bilateral=BilateralOps(
            high_mid=float(bil.get("high_mid", 0.90)),
            low_mid=float(bil.get("low_mid", 0.10)),
        ),
        fill_handler=FillHandlerOps(
            exit_within_seconds=float(fh.get("exit_within_seconds", 60)),
            queue_depletion_usd=float(fh.get("queue_depletion_usd", 300)),
            vol_drop_pct=float(fh.get("vol_drop_pct", 0.25)),
            exit_loss_ticks=int(fh.get("exit_loss_ticks", 1)),
        ),
    )
