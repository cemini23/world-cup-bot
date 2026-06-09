"""K107 cluster repricing telemetry — fear-index style cohort mid velocity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from world_cup_bot.k107_posture import ClusterRepricingConfig
from world_cup_bot.ledger import load_rows
from world_cup_bot.scanner import AdvanceMarket


@dataclass(frozen=True)
class ClusterRepricingSummary:
    markets_tracked: int
    markets_with_prior: int
    markets_moved: int
    median_abs_delta_pp: float | None
    max_abs_delta_pp: float | None
    cluster_speed_pp_per_hour: float | None
    fear_index_tier: str  # calm | elevated | fast | insufficient_data
    hours_since_prior: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "markets_tracked": self.markets_tracked,
            "markets_with_prior": self.markets_with_prior,
            "markets_moved": self.markets_moved,
            "median_abs_delta_pp": self.median_abs_delta_pp,
            "max_abs_delta_pp": self.max_abs_delta_pp,
            "cluster_speed_pp_per_hour": self.cluster_speed_pp_per_hour,
            "fear_index_tier": self.fear_index_tier,
            "hours_since_prior": self.hours_since_prior,
        }


def mids_from_markets(markets: list[AdvanceMarket]) -> dict[str, float]:
    return {m.team: float(m.mid) for m in markets if m.mid is not None}


def _parse_ts(raw: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (TypeError, ValueError):
        return None


def last_mid_snapshot(ledger_path: Path) -> tuple[datetime | None, dict[str, float]]:
    if not ledger_path.is_file():
        return None, {}
    for row in reversed(load_rows(ledger_path)):
        if row.get("event") != "market_mid_snapshot":
            continue
        mids_raw = row.get("mids") or {}
        if not isinstance(mids_raw, dict):
            continue
        ts = _parse_ts(str(row.get("timestamp") or ""))
        mids = {str(k): float(v) for k, v in mids_raw.items()}
        return ts, mids
    return None, {}


def _tier_for_speed(
    speed: float | None,
    cfg: ClusterRepricingConfig,
) -> str:
    if speed is None:
        return "insufficient_data"
    if speed >= cfg.fast_repricing_pp_per_hour:
        return "fast"
    if speed >= cfg.elevated_repricing_pp_per_hour:
        return "elevated"
    return "calm"


def analyze_cluster_repricing(
    markets: list[AdvanceMarket],
    ledger_path: Path,
    cfg: ClusterRepricingConfig,
) -> ClusterRepricingSummary:
    current = mids_from_markets(markets)
    prior_ts, prior = last_mid_snapshot(ledger_path)

    if len(current) < cfg.min_markets or not prior or prior_ts is None:
        return ClusterRepricingSummary(
            markets_tracked=len(current),
            markets_with_prior=len(set(current) & set(prior)),
            markets_moved=0,
            median_abs_delta_pp=None,
            max_abs_delta_pp=None,
            cluster_speed_pp_per_hour=None,
            fear_index_tier="insufficient_data",
            hours_since_prior=None,
        )

    now = datetime.now(tz=UTC)
    hours = max((now - prior_ts).total_seconds() / 3600.0, 1.0 / 60.0)
    deltas: list[float] = []
    moved = 0
    for team, live_mid in current.items():
        old = prior.get(team)
        if old is None:
            continue
        delta_pp = abs(live_mid - old) * 100.0
        deltas.append(delta_pp)
        if delta_pp >= 0.5:
            moved += 1

    if not deltas:
        return ClusterRepricingSummary(
            markets_tracked=len(current),
            markets_with_prior=0,
            markets_moved=0,
            median_abs_delta_pp=None,
            max_abs_delta_pp=None,
            cluster_speed_pp_per_hour=None,
            fear_index_tier="insufficient_data",
            hours_since_prior=round(hours, 3),
        )

    med = median(deltas)
    mx = max(deltas)
    speed = med / hours
    return ClusterRepricingSummary(
        markets_tracked=len(current),
        markets_with_prior=len(deltas),
        markets_moved=moved,
        median_abs_delta_pp=round(med, 3),
        max_abs_delta_pp=round(mx, 3),
        cluster_speed_pp_per_hour=round(speed, 3),
        fear_index_tier=_tier_for_speed(speed, cfg),
        hours_since_prior=round(hours, 3),
    )


def snapshot_fields(markets: list[AdvanceMarket]) -> dict[str, float]:
    return mids_from_markets(markets)
