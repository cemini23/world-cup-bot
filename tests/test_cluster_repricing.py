"""Tests for K107 cluster repricing telemetry."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from market_helpers import make_market
from world_cup_bot.cluster_repricing import analyze_cluster_repricing
from world_cup_bot.k107_posture import ClusterRepricingConfig
from world_cup_bot.ledger import record_diagnostic
from world_cup_bot.logic_version import load_strategy_version


def test_cluster_repricing_elevated_tier(tmp_path: Path):
    spec = load_strategy_version()
    ledger = tmp_path / "ledger.jsonl"
    mids = {"Brazil": 0.50, "France": 0.60, "Germany": 0.55}
    record_diagnostic(
        spec,
        path=ledger,
        event="market_mid_snapshot",
        fields={"mids": mids},
    )
    prior_ts = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()
    rows = ledger.read_text().strip().split("\n")
    row = json.loads(rows[-1])
    row["timestamp"] = prior_ts
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")

    markets = [
        make_market(team="Brazil", mid=0.54),
        make_market(team="France", mid=0.66),
        make_market(team="Germany", mid=0.60),
        make_market(team="Spain", mid=0.40),
        make_market(team="Japan", mid=0.35),
    ]
    cfg = ClusterRepricingConfig(
        min_markets=3,
        fast_repricing_pp_per_hour=10.0,
        elevated_repricing_pp_per_hour=0.01,
    )
    summary = analyze_cluster_repricing(markets, ledger, cfg)
    assert summary.markets_with_prior >= 3
    assert summary.fear_index_tier in ("elevated", "fast")
    assert summary.cluster_speed_pp_per_hour is not None


def test_cluster_repricing_insufficient_without_prior(tmp_path: Path):
    cfg = ClusterRepricingConfig(min_markets=2)
    markets = [make_market(team="Brazil", mid=0.5), make_market(team="France", mid=0.6)]
    summary = analyze_cluster_repricing(markets, tmp_path / "empty.jsonl", cfg)
    assert summary.fear_index_tier == "insufficient_data"
