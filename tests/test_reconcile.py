"""Tests for REST → WS trade reconciliation."""

from market_helpers import make_market
from world_cup_bot import ws_user
from world_cup_bot.clob_auth import ClobAuth
from world_cup_bot.logic_version import load_strategy_version
from world_cup_bot.operating_config import load_operating_config
from world_cup_bot.reconcile import ReconcileState, rest_trade_to_ws_message, run_reconcile_pass


def test_rest_trade_to_ws_message():
    trade = {
        "id": "trade-1",
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
