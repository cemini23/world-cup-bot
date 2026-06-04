"""LP promotion gate tests."""

from datetime import UTC, datetime
from pathlib import Path

from world_cup_bot import ledger
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.lp_promotion import compute_promotion_metrics, evaluate_promotion_gates
from world_cup_bot.operating_config import PromotionOps


def _spec() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        strategy_key="pm_wc_advance_lp",
        version_id="wc_advance_lp_v4",
        deployed_at=datetime.now(UTC),
        note="",
        legacy_version_ids=frozenset(),
    )


def _promo() -> PromotionOps:
    return PromotionOps(min_fills=2, min_distinct_days=2, min_dsr=0.0, max_mcpt_p=0.50)


def test_promotion_na_without_fills(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    ok, detail, metrics = evaluate_promotion_gates(path, _spec(), _promo())
    assert ok is True
    assert "n/a" in detail
    assert metrics.fill_count == 0


def test_promotion_passes_with_positive_daily_pnl(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    spec = _spec()
    for day, pnl in (("2026-06-01", 10.0), ("2026-06-02", 5.0)):
        ledger.append_row(
            path,
            ledger.LedgerRow(
                event="order_fill",
                logic_version=spec.version_id,
                strategy_key=spec.strategy_key,
                timestamp=f"{day}T12:00:00+00:00",
                pnl_usd=pnl,
            ),
        )
    metrics = compute_promotion_metrics(path, spec)
    assert metrics.fill_count == 2
    assert metrics.distinct_days == 2
    ok, detail, _ = evaluate_promotion_gates(path, spec, _promo())
    assert ok is True
    assert "pass" in detail
