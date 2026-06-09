"""K107 — pre-kickoff liquidity posture (inflow environment flag, quote-cap guard)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from world_cup_bot.paths import resolve_project_path


@dataclass(frozen=True)
class ClusterRepricingConfig:
    enabled: bool = True
    min_markets: int = 5
    fast_repricing_pp_per_hour: float = 3.0
    elevated_repricing_pp_per_hour: float = 1.5


@dataclass(frozen=True)
class LpSafetyDrConfig:
    interval_days: int = 7
    last_run_marker: str = "data/local/k107_lp_safety_last_run.txt"


@dataclass(frozen=True)
class K107PostureConfig:
    pre_kickoff_inflow_headline: bool = False
    block_volume_based_cap_scaling: bool = True
    cluster_repricing: ClusterRepricingConfig = ClusterRepricingConfig()
    lp_safety_dr: LpSafetyDrConfig = LpSafetyDrConfig()


def load_k107_posture(path: Path | None = None) -> K107PostureConfig:
    cfg_path = path or resolve_project_path("config/k107_liquidity_posture.yaml")
    if not cfg_path.is_file():
        return K107PostureConfig()
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cluster_raw = raw.get("cluster_repricing") or {}
    lp_raw = raw.get("lp_safety_dr") or {}
    return K107PostureConfig(
        pre_kickoff_inflow_headline=bool(raw.get("pre_kickoff_inflow_headline", False)),
        block_volume_based_cap_scaling=bool(raw.get("block_volume_based_cap_scaling", True)),
        cluster_repricing=ClusterRepricingConfig(
            enabled=bool(cluster_raw.get("enabled", True)),
            min_markets=int(cluster_raw.get("min_markets", 5)),
            fast_repricing_pp_per_hour=float(cluster_raw.get("fast_repricing_pp_per_hour", 3.0)),
            elevated_repricing_pp_per_hour=float(
                cluster_raw.get("elevated_repricing_pp_per_hour", 1.5)
            ),
        ),
        lp_safety_dr=LpSafetyDrConfig(
            interval_days=int(lp_raw.get("interval_days", 7)),
            last_run_marker=str(
                lp_raw.get("last_run_marker", "data/local/k107_lp_safety_last_run.txt")
            ),
        ),
    )


def environment_telemetry(cfg: K107PostureConfig) -> dict[str, Any]:
    return {
        "k107_pre_kickoff_inflow_headline": cfg.pre_kickoff_inflow_headline,
        "k107_block_volume_cap_scaling": cfg.block_volume_based_cap_scaling,
    }


def clamp_notional_multiplier(
    multiplier: float,
    *,
    volume_scale: float = 1.0,
    cfg: K107PostureConfig,
) -> float:
    """Drop volume-headline scaling when K107 block is active; keep conviction/streak caps."""
    if cfg.block_volume_based_cap_scaling and volume_scale != 1.0:
        return multiplier
    if cfg.block_volume_based_cap_scaling:
        return multiplier
    return multiplier * volume_scale


def lp_safety_marker_path(cfg: K107PostureConfig) -> Path:
    return resolve_project_path(cfg.lp_safety_dr.last_run_marker)


def lp_safety_due(cfg: K107PostureConfig, *, now: datetime | None = None) -> bool:
    marker = lp_safety_marker_path(cfg)
    if not marker.is_file():
        return True
    now = now or datetime.now(tz=UTC)
    try:
        raw = marker.read_text(encoding="utf-8").strip()
        last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
    except (OSError, ValueError):
        return True
    return now - last >= timedelta(days=cfg.lp_safety_dr.interval_days)


def mark_lp_safety_run(cfg: K107PostureConfig, *, now: datetime | None = None) -> None:
    marker = lp_safety_marker_path(cfg)
    marker.parent.mkdir(parents=True, exist_ok=True)
    ts = (now or datetime.now(tz=UTC)).isoformat()
    marker.write_text(ts, encoding="utf-8")
