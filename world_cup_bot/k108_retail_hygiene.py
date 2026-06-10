"""K108 retail hygiene — sports fee telemetry on plan / negative_filter_summary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from world_cup_bot.paths import resolve_project_path


@dataclass(frozen=True)
class K108RetailHygieneConfig:
    sports_taker_fee_peak_pct: float = 0.75
    round_trip_fee_pct_low: float = 1.0
    round_trip_fee_pct_high: float = 2.0
    sports_fee_schedule_url: str = ""


def load_k108_retail_hygiene(path: Path | None = None) -> K108RetailHygieneConfig:
    cfg_path = path or resolve_project_path("config/k108_retail_hygiene.yaml")
    if not cfg_path.is_file():
        return K108RetailHygieneConfig()
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return K108RetailHygieneConfig(
        sports_taker_fee_peak_pct=float(raw.get("sports_taker_fee_peak_pct", 0.75)),
        round_trip_fee_pct_low=float(raw.get("round_trip_fee_pct_low", 1.0)),
        round_trip_fee_pct_high=float(raw.get("round_trip_fee_pct_high", 2.0)),
        sports_fee_schedule_url=str(raw.get("sports_fee_schedule_url") or ""),
    )


def negative_filter_telemetry(cfg: K108RetailHygieneConfig) -> dict[str, Any]:
    return {
        "sports_taker_fee_model_pp": cfg.sports_taker_fee_peak_pct,
        "sports_round_trip_fee_pp_low": cfg.round_trip_fee_pct_low,
        "sports_round_trip_fee_pp_high": cfg.round_trip_fee_pct_high,
    }


def post_fee_mid_edge_pp(raw_edge_pp: float, cfg: K108RetailHygieneConfig) -> float:
    """Subtract conservative round-trip taker fee estimate from raw mid edge (pp)."""
    return raw_edge_pp - cfg.round_trip_fee_pct_high
