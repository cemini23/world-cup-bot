"""Tests for user-channel WebSocket fill parsing (Module 4 wiring)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from market_helpers import make_market
from world_cup_bot import fill_handler, ledger, ws_user
from world_cup_bot.clob_auth import ClobAuth
from world_cup_bot.logic_version import load_strategy_version
from world_cup_bot.operating_config import load_operating_config

FIXTURE = Path(__file__).parent / "fixtures" / "user_channel_trade_matched.json"


def _load_trade_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_build_user_subscription():
    auth = ClobAuth(api_key="key", secret="sec", passphrase="pp")
    sub = ws_user.build_user_subscription(auth, ["0xabc", "0xdef"])
    assert sub["type"] == "user"
    assert sub["auth"]["apiKey"] == "key"
    assert sub["markets"] == ["0xabc", "0xdef"]


def test_parse_ws_text_pong():
    assert ws_user.parse_ws_text("PONG") is None


def test_extract_maker_fills_from_fixture():
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    msg = _load_trade_fixture()
    fills = ws_user.extract_maker_fills(msg, {"0x1": market})
    assert len(fills) == 1
    fill = fills[0]
    assert fill.order_id == "0xff354cd7ca7539dfa9c28d90943ab5779a4eac34b9b37a757d7b32bdfb11790b"
    assert fill.team == "Turkey"
    assert fill.side == "YES"
    assert fill.fill_price == 0.44
    assert fill.fill_shares == 500.0
    assert fill.filled_at == ws_user._parse_timestamp(msg)


def test_extract_maker_fills_skips_sell_maker_leg():
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    msg = _load_trade_fixture()
    msg["maker_orders"] = [
        {
            "asset_id": "yes",
            "matched_amount": "500",
            "order_id": "0xexit-sell-order",
            "outcome": "YES",
            "price": "0.43",
            "side": "SELL",
        }
    ]
    assert ws_user.extract_maker_fills(msg, {"0x1": market}) == []


def test_process_trade_skips_sell_maker_leg(tmp_path: Path):
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={"0x1": market},
        markets=[market],
        operating=load_operating_config(),
        version_spec=load_strategy_version(),
        ledger_path=str(tmp_path / "ledger.jsonl"),
        dry_run=False,
        record=True,
    )
    msg = _load_trade_fixture()
    msg["id"] = "sell-fill-trade"
    msg["maker_orders"] = [
        {
            "asset_id": "yes",
            "matched_amount": "500",
            "order_id": "0xexit-sell-order",
            "outcome": "YES",
            "price": "0.43",
            "side": "SELL",
        }
    ]
    with patch("world_cup_bot.ws_user.submit_exit") as submit_exit:
        results = ws_user.process_trade_message(msg, ctx)
    assert results == []
    assert ctx.stats.fills_processed == 0
    submit_exit.assert_not_called()


def test_skips_non_matched_status():
    market = make_market("Turkey", mid=0.45)
    msg = _load_trade_fixture()
    msg["status"] = "CONFIRMED"
    assert ws_user.extract_maker_fills(msg, {"0x1": market}) == []


def test_process_trade_message_dedup():
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
    msg = _load_trade_fixture()
    first = ws_user.process_trade_message(msg, ctx)
    second = ws_user.process_trade_message(msg, ctx)
    assert len(first) == 1
    assert len(second) == 0
    assert ctx.stats.fills_processed == 1
    assert ctx.stats.fills_skipped_dedup == 1
    assert isinstance(first[0], fill_handler.FillHandlerResult)


def test_process_trade_skips_exit_when_ledger_dedups_order_id(tmp_path: Path):
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    ledger_path = tmp_path / "ledger.jsonl"
    version_spec = load_strategy_version()
    msg = _load_trade_fixture()
    fill = ws_user.extract_maker_fills(msg, {"0x1": market})[0]
    ledger.record_fill(
        path=ledger_path,
        spec=version_spec,
        team=fill.team,
        side=fill.side,
        order_id=fill.order_id,
        price=fill.fill_price,
        size_shares=fill.fill_shares,
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={"0x1": market},
        markets=[market],
        operating=load_operating_config(),
        version_spec=version_spec,
        ledger_path=str(ledger_path),
        dry_run=False,
        record=True,
    )
    msg2 = dict(msg)
    msg2["id"] = "different-trade-id"
    with patch("world_cup_bot.ws_user.submit_exit") as submit_exit:
        results = ws_user.process_trade_message(msg2, ctx)
    assert results == []
    assert ctx.stats.fills_skipped_dedup == 1
    submit_exit.assert_not_called()


def test_process_trade_unknown_market_increments_skip():
    ctx = ws_user.FillWatchContext(
        markets_by_condition={},
        markets=[],
        operating=load_operating_config(),
        version_spec=load_strategy_version(),
        ledger_path="data/local/test-ledger.jsonl",
        dry_run=True,
        record=False,
    )
    msg = _load_trade_fixture()
    assert ws_user.process_trade_message(msg, ctx) == []
    assert ctx.stats.fills_skipped_unknown_market == 1


def test_process_trade_queue_depletion(monkeypatch):
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
    monkeypatch.setattr(
        "world_cup_bot.ws_user.fetch_ahead_bid_notional_usd",
        lambda *_a, **_k: 200.0,
    )
    msg = _load_trade_fixture()
    results = ws_user.process_trade_message(msg, ctx)
    assert len(results) == 1
    assert results[0].pull_quotes
    assert "queue depletion" in results[0].reason


def test_parse_timestamp_skips_invalid_then_uses_next_key():
    msg = {"timestamp": "not-a-ts", "matchtime": "1717248000"}
    parsed = ws_user._parse_timestamp(msg)
    assert parsed == ws_user._parse_timestamp({"matchtime": "1717248000"})


def test_hydrate_watch_context_seeds_ledger_order_ids(tmp_path: Path):
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    ledger_path = tmp_path / "ledger.jsonl"
    version_spec = load_strategy_version()
    ledger.record_fill(
        path=ledger_path,
        spec=version_spec,
        team="Turkey",
        side="YES",
        order_id="0xhydrate",
        price=0.44,
        size_shares=100.0,
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={"0x1": market},
        markets=[market],
        operating=load_operating_config(),
        version_spec=version_spec,
        ledger_path=str(ledger_path),
        dry_run=True,
        record=False,
    )
    ws_user.hydrate_watch_context(ctx)
    assert "ledger:0xhydrate" in ctx.seen_fill_keys
    assert ctx.reconcile_state.last_after_ts is not None


def test_market_safety_vol_pull_respects_cooldown(monkeypatch):
    from world_cup_bot.config import Settings

    market = make_market("Turkey", mid=0.35, hours_to_kickoff=48.0)
    market = market.__class__(
        **{**market.__dict__, "condition_id": "0x1", "yes_token_id": "yes", "no_token_id": "no"}
    )
    settings = Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://example.com/ws",
        ws_market_url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
        data_api_url="https://data-api.polymarket.com",
        match_shock_tape_dir="data/local/shock_tapes",
        match_shock_ledger_path="data/local/match_shock_paper.jsonl",
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path="data/local/test-ledger.jsonl",
        operating_config="config/operating.yaml",
        cross_venue_config="config/cross_venue.yaml",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
        market_phases_config="config/market_phases.yaml",
    )
    ctx = ws_user.FillWatchContext(
        markets_by_condition={"0x1": market},
        markets=[market],
        operating=load_operating_config(),
        version_spec=load_strategy_version(),
        ledger_path="data/local/test-ledger.jsonl",
        dry_run=True,
        record=False,
        settings=settings,
    )
    ctx.peak_mid_by_team["Turkey"] = 0.50
    pulled: list[str] = []

    def fake_apply(_settings, _markets, *, team, pull_quotes, **_kwargs):
        if pull_quotes:
            pulled.append(team)

    monkeypatch.setattr(
        "world_cup_bot.ws_user.discover_advance_markets",
        lambda *_a, **_k: [market],
    )
    monkeypatch.setattr("world_cup_bot.order_manager.apply_fill_safety_actions", fake_apply)
    monkeypatch.setattr(
        "world_cup_bot.order_manager.cancel_for_cancel_window",
        lambda *_a, **_k: None,
    )

    ws_user.market_safety_pass(ctx)
    assert pulled == ["Turkey"]
    ws_user.market_safety_pass(ctx)
    assert pulled == ["Turkey"]
