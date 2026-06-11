"""Tests for REST → WS trade reconciliation."""

import pytest

from market_helpers import make_market
from world_cup_bot import ws_user
from world_cup_bot.clob_auth import ClobAuth
from world_cup_bot.logic_version import load_strategy_version
from world_cup_bot.operating_config import load_operating_config
from world_cup_bot.reconcile import ReconcileState, rest_trade_to_ws_message, run_reconcile_pass


@pytest.mark.parametrize(
    "status",
    ["CONFIRMED", "MINED", "TRADE_STATUS_CONFIRMED", "TRADE_STATUS_MINED"],
)
def test_rest_trade_to_ws_message(status: str):
    trade = {
        "id": "trade-1",
        "market": "0x1",
        "status": status,
        "match_time": "1717248000",
        "maker_orders": [
            {
                "order_id": "0xorder",
                "outcome": "YES",
                "price": "0.44",
                "matched_amount": "500",
                "asset_id": "yes",
            }
        ],
    }
    msg = rest_trade_to_ws_message(trade)
    assert msg["status"] == "MATCHED"
    assert ws_user.is_matched_trade_message(msg)


def test_run_reconcile_pass_processes_missed_fill(monkeypatch):
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={"0x1": market},
        markets=[market],
        operating=load_operating_config(),
        version_spec=load_strategy_version(),
        ledger_path="data/local/test-ledger.jsonl",
        dry_run=True,
        record=False,
    )
    auth = ClobAuth(api_key="k", secret="c2VjcmV0", passphrase="p")

    trade = {
        "id": "rest-trade-1",
        "market": "0x1",
        "status": "TRADE_STATUS_CONFIRMED",
        "match_time": "1717248000",
        "maker_orders": [
            {
                "order_id": "0xorder",
                "outcome": "YES",
                "price": "0.44",
                "matched_amount": "500",
                "asset_id": "yes",
            }
        ],
    }

    def fake_fetch_trades(*_args, **_kwargs):
        return [trade]

    monkeypatch.setattr("world_cup_bot.reconcile.fetch_trades", fake_fetch_trades)

    state = ReconcileState()
    stats = run_reconcile_pass(
        clob_url="https://clob.polymarket.com",
        auth=auth,
        poly_address="0xsigner",
        maker_address="0xmaker",
        ctx=ctx,
        state=state,
    )
    assert stats.trades_fetched == 1
    assert stats.fills_processed == 1
    assert ctx.stats.fills_processed == 1


def test_run_reconcile_pass_does_not_advance_cursor_on_pending(monkeypatch):
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={"0x1": market},
        markets=[market],
        operating=load_operating_config(),
        version_spec=load_strategy_version(),
        ledger_path="data/local/test-ledger.jsonl",
        dry_run=True,
        record=False,
    )
    auth = ClobAuth(api_key="k", secret="c2VjcmV0", passphrase="p")
    pending = {
        "id": "pending-trade",
        "market": "0x1",
        "status": "PENDING",
        "match_time": "2000000000",
        "maker_orders": [],
    }

    monkeypatch.setattr("world_cup_bot.reconcile.fetch_trades", lambda *_a, **_k: [pending])

    state = ReconcileState()
    state.last_after_ts = 1000
    stats = run_reconcile_pass(
        clob_url="https://clob.polymarket.com",
        auth=auth,
        poly_address="0xsigner",
        maker_address="0xmaker",
        ctx=ctx,
        state=state,
    )
    assert stats.trades_fetched == 1
    assert stats.fills_processed == 0
    assert state.last_after_ts == 1000


def test_run_reconcile_pass_caps_cursor_when_pending_and_confirmed_in_batch(monkeypatch):
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={"0x1": market},
        markets=[market],
        operating=load_operating_config(),
        version_spec=load_strategy_version(),
        ledger_path="data/local/test-ledger.jsonl",
        dry_run=True,
        record=False,
    )
    auth = ClobAuth(api_key="k", secret="c2VjcmV0", passphrase="p")
    pending = {
        "id": "pending-trade",
        "market": "0x1",
        "status": "PENDING",
        "match_time": "2000000000",
        "maker_orders": [],
    }
    confirmed = {
        "id": "confirmed-trade",
        "market": "0x1",
        "status": "TRADE_STATUS_CONFIRMED",
        "match_time": "3000000000",
        "maker_orders": [
            {
                "order_id": "0xorder3",
                "outcome": "YES",
                "price": "0.44",
                "matched_amount": "100",
                "asset_id": "yes",
            }
        ],
    }

    monkeypatch.setattr(
        "world_cup_bot.reconcile.fetch_trades",
        lambda *_a, **_k: [pending, confirmed],
    )

    state = ReconcileState()
    state.last_after_ts = 1000
    run_reconcile_pass(
        clob_url="https://clob.polymarket.com",
        auth=auth,
        poly_address="0xsigner",
        maker_address="0xmaker",
        ctx=ctx,
        state=state,
    )
    assert state.last_after_ts == 1999999999


def test_run_reconcile_pass_advances_cursor_on_processed_trade(monkeypatch):
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={"0x1": market},
        markets=[market],
        operating=load_operating_config(),
        version_spec=load_strategy_version(),
        ledger_path="data/local/test-ledger.jsonl",
        dry_run=True,
        record=False,
    )
    auth = ClobAuth(api_key="k", secret="c2VjcmV0", passphrase="p")
    trade = {
        "id": "rest-trade-2",
        "market": "0x1",
        "status": "TRADE_STATUS_CONFIRMED",
        "match_time": "2000000000",
        "maker_orders": [
            {
                "order_id": "0xorder2",
                "outcome": "YES",
                "price": "0.44",
                "matched_amount": "100",
                "asset_id": "yes",
            }
        ],
    }

    monkeypatch.setattr("world_cup_bot.reconcile.fetch_trades", lambda *_a, **_k: [trade])

    state = ReconcileState()
    state.last_after_ts = 1000
    run_reconcile_pass(
        clob_url="https://clob.polymarket.com",
        auth=auth,
        poly_address="0xsigner",
        maker_address="0xmaker",
        ctx=ctx,
        state=state,
    )
    assert state.last_after_ts == 2000000000
