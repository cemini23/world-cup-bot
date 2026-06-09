import json
from pathlib import Path

import pytest

from world_cup_bot import ledger
from world_cup_bot.logic_version import LEGACY_UNVERSIONED, PnlScope, load_strategy_version
from world_cup_bot.quoter import MarketSnapshot, QuoteIntent


@pytest.fixture
def version_spec():
    return load_strategy_version()


@pytest.fixture
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.jsonl"


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        mid=0.45,
        best_bid=0.43,
        best_ask=0.47,
        spread=0.04,
        rewards_min_shares=500,
        rewards_max_spread=4.5,
        hours_to_kickoff=48.0,
    )


def _intent(**overrides) -> QuoteIntent:
    base = dict(
        team="Turkey",
        side="YES",
        token_id="111",
        order_id="dry-turkey-yes-test0001",
        price=0.44,
        size_shares=100.0,
        notional_usd=44.0,
        dry_run=True,
        reason="test",
        snapshot=_snapshot(),
    )
    base.update(overrides)
    return QuoteIntent(**base)


def test_load_rows_skips_corrupt_lines(version_spec, ledger_path):
    ledger_path.write_text(
        '{"event":"order_fill","logic_version":"x"}\n'
        "not json\n"
        '{"event":"quote_intent","logic_version":"'
        f'{version_spec.version_id}"}}\n'
    )
    rows = ledger.load_rows(ledger_path)
    assert len(rows) == 2
    assert rows[0]["event"] == "order_fill"
    assert rows[1]["event"] == "quote_intent"


def test_watch_ledger_seed_from_fills(version_spec, ledger_path):
    ledger.record_fill(
        path=ledger_path,
        spec=version_spec,
        team="Turkey",
        side="YES",
        order_id="0xabc",
        price=0.44,
        size_shares=100.0,
    )
    seed = ledger.watch_ledger_seed(ledger_path, version_spec)
    assert "0xabc" in seed.seen_order_ids
    assert seed.last_fill_epoch is not None


def test_load_rows_accepts_str_path(version_spec, ledger_path):
    ledger.append_row(
        str(ledger_path),
        ledger.LedgerRow(
            event="reward_accrual",
            logic_version=version_spec.version_id,
            strategy_key=version_spec.strategy_key,
            timestamp="2026-05-30T12:00:00+00:00",
            rewards_usd=1.0,
        ),
    )
    rows = ledger.load_rows(str(ledger_path))
    assert len(rows) == 1
    assert rows[0]["event"] == "reward_accrual"


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
    n = ledger.record_quote_intents(
        [_intent()],
        version_spec,
        path=ledger_path,
        dry_run=True,
        correlation_id="test-run",
    )
    assert n == 1

    rows = ledger.load_rows(ledger_path)
    assert rows[0]["event"] == "quote_intent_dry_run"
    assert rows[0]["logic_version"] == version_spec.version_id
    assert rows[0]["correlation_id"] == "test-run"
    assert rows[0]["order_id"] == "dry-turkey-yes-test0001"
    assert rows[0]["mid_at_place"] == pytest.approx(0.45)
    assert rows[0]["rewards_max_spread"] == pytest.approx(4.5)

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


def test_fill_dedup(version_spec, ledger_path):
    ok1 = ledger.record_fill(
        path=ledger_path,
        spec=version_spec,
        team="Turkey",
        side="YES",
        order_id="ord-dup",
        price=0.50,
        size_shares=100,
    )
    ok2 = ledger.record_fill(
        path=ledger_path,
        spec=version_spec,
        team="Turkey",
        side="YES",
        order_id="ord-dup",
        price=0.50,
        size_shares=100,
    )
    assert ok1 is True
    assert ok2 is False
    rows = ledger.load_rows(ledger_path)
    summary = ledger.summarize_pnl(rows, version_spec, PnlScope.CURRENT)
    assert summary.fills == 1


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


def test_position_exit_realized_pnl(version_spec, ledger_path):
    ledger.record_position_exit(
        path=ledger_path,
        spec=version_spec,
        team="Turkey",
        side="YES",
        entry_order_id="entry-1",
        exit_order_id="exit-1",
        entry_price=0.44,
        exit_price=0.52,
        size_shares=100.0,
        pnl_usd=8.0,
        dry_run=False,
    )
    rows = ledger.load_rows(ledger_path)
    summary = ledger.summarize_pnl(rows, version_spec, PnlScope.CURRENT)
    assert summary.realized_pnl_usd == pytest.approx(8.0)
    assert summary.fills == 0
