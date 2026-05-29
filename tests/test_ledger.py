import json
from pathlib import Path

import pytest

from world_cup_bot import ledger
from world_cup_bot.logic_version import LEGACY_UNVERSIONED, PnlScope, load_strategy_version
from world_cup_bot.quoter import QuoteIntent


@pytest.fixture
def version_spec():
    return load_strategy_version()


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.jsonl"


def test_filter_scope_current(version_spec):
    rows = [
        {"logic_version": version_spec.version_id, "event": "order_fill", "pnl_usd": 10},
        {"logic_version": LEGACY_UNVERSIONED, "event": "order_fill", "pnl_usd": -50},
        {"logic_version": "old_v0", "event": "order_fill", "pnl_usd": -5},
    ]
    from world_cup_bot.logic_version import filter_rows_by_scope

    scoped = filter_rows_by_scope(rows, version_spec, PnlScope.CURRENT)
    assert len(scoped) == 1
    assert scoped[0]["pnl_usd"] == 10


def test_record_and_summarize(version_spec, ledger_path):
    intents = [
        QuoteIntent(
            team="Turkey",
            side="YES",
            token_id="111",
            price=0.44,
            size_shares=100.0,
            notional_usd=44.0,
            dry_run=True,
            reason="test",
        )
    ]
    n = ledger.record_quote_intents(
        intents, version_spec, path=ledger_path, dry_run=True, correlation_id="test-run"
    )
    assert n == 1

    rows = ledger.load_rows(ledger_path)
    assert rows[0]["event"] == "quote_intent_dry_run"
    assert rows[0]["logic_version"] == version_spec.version_id
    assert rows[0]["correlation_id"] == "test-run"

    summary = ledger.summarize_pnl(rows, version_spec, PnlScope.CURRENT)
    assert summary.quote_intents == 1
    assert summary.fills == 0
    assert summary.net_pnl_usd == 0.0


def test_fill_pnl_net(version_spec, ledger_path):
    ledger.record_fill(
        path=ledger_path,
        spec=version_spec,
        team="Turkey",
        side="YES",
        order_id="ord-1",
        price=0.50,
        size_shares=100,
        pnl_usd=-12.5,
        fees_usd=0.5,
    )
    ledger.append_row(
        ledger_path,
        ledger.LedgerRow(
            event="reward_accrual",
            logic_version=version_spec.version_id,
            strategy_key=version_spec.strategy_key,
            timestamp="2026-05-30T12:00:00+00:00",
            rewards_usd=25.0,
        ),
    )

    rows = ledger.load_rows(ledger_path)
    summary = ledger.summarize_pnl(rows, version_spec, PnlScope.CURRENT)
    assert summary.fills == 1
    assert summary.realized_pnl_usd == pytest.approx(-12.5)
    assert summary.rewards_usd == pytest.approx(25.0)
    assert summary.fees_usd == pytest.approx(0.5)
    assert summary.net_pnl_usd == pytest.approx(12.0)


def test_legacy_excluded_in_summary(version_spec, ledger_path):
    with ledger_path.open("w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "event": "order_fill",
                    "logic_version": LEGACY_UNVERSIONED,
                    "pnl_usd": -999,
                }
            )
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "event": "order_fill",
                    "logic_version": version_spec.version_id,
                    "pnl_usd": 5,
                }
            )
            + "\n"
        )

    rows = ledger.load_rows(ledger_path)
    summary = ledger.summarize_pnl(rows, version_spec, PnlScope.CURRENT)
    assert summary.legacy_excluded == 1
    assert summary.realized_pnl_usd == pytest.approx(5.0)
