"""Ledger cancel audit trail."""

from datetime import UTC, datetime
from pathlib import Path

from world_cup_bot import ledger
from world_cup_bot.logic_version import StrategyVersionSpec


def _spec() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        strategy_key="pm_wc_advance_lp",
        version_id="wc_advance_lp_v4",
        deployed_at=datetime.now(UTC),
        note="test",
        legacy_version_ids=frozenset(),
    )


def test_record_order_cancel_appends_dry_run_event(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    spec = _spec()
    ledger.record_order_cancel(
        spec,
        path=path,
        order_ids=["ord-1", "ord-2"],
        reason="calendar cancel window",
        teams=("Turkey",),
        dry_run=True,
    )
    rows = ledger.load_rows(path)
    assert len(rows) == 1
    row = rows[0]
    assert row["event"] == "order_cancel_dry_run"
    assert row["logic_version"] == "wc_advance_lp_v4"
    assert row["reason"] == "calendar cancel window"
    assert row["order_ids"] == ["ord-1", "ord-2"]
    assert row["teams"] == ["Turkey"]


def test_cancel_orders_records_ledger(monkeypatch, tmp_path: Path):
    from dataclasses import replace

    from world_cup_bot import order_manager
    from world_cup_bot.config import Settings

    settings = replace(Settings.from_env(), dry_run=True, ledger_path=str(tmp_path / "l.jsonl"))
    spec = _spec()
    order = order_manager.OpenOrder(
        order_id="x-1",
        asset_id="tok",
        condition_id="0x1",
        side="BUY",
        price=0.5,
        size=10.0,
        status="LIVE",
        team="Turkey",
    )
    monkeypatch.setattr(order_manager, "_cancel_order_ids", lambda *a, **k: ["x-1"])
    monkeypatch.setattr("world_cup_bot.alerts.notify", lambda *a, **k: False)

    order_manager.cancel_orders(
        settings,
        [order],
        reason="test cancel",
        ledger_path=settings.ledger_path,
        version_spec=spec,
    )
    rows = ledger.load_rows(Path(settings.ledger_path))
    assert rows[0]["event"] == "order_cancel_dry_run"
    assert rows[0]["order_count"] == 1
