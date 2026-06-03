"""Tests for match_shock_ledger."""

from __future__ import annotations

from pathlib import Path

from world_cup_bot.match_shock import LadderOrder, LadderPlan, ShockDetection
from world_cup_bot.match_shock_ledger import (
    load_shock_rows,
    record_ladder_planned,
    record_paper_fill,
    record_shock_detected,
)


def test_ledger_round_trip(tmp_path: Path):
    path = tmp_path / "shock.jsonl"
    detection = ShockDetection(
        shock=True,
        peak=0.30,
        floor=0.20,
        depth=0.10,
        pre_price=0.30,
    )
    record_shock_detected(
        path,
        slug="epl-test",
        detection=detection,
        bucket_key="k",
        depth_cents=10.0,
    )
    plan = LadderPlan(
        bucket_key="deep|underdog|balanced|early|level",
        pre_price=0.30,
        percentiles_cents={50: 8.0},
        orders=(LadderOrder(50, 0.22, 5.0, 0.1),),
        recovery_target_price=0.26,
    )
    record_ladder_planned(path, slug="epl-test", plan=plan)
    fill = LadderOrder(50, 0.22, 5.0, 0.1)
    record_paper_fill(path, slug="epl-test", plan=plan, fill=fill, pnl_usd=1.5)
    rows = load_shock_rows(path)
    assert len(rows) == 3
    assert rows[0]["event"] == "match_shock_detected"
    assert rows[2]["event"] == "match_shock_paper_fill"
