"""Tests for order manager — cancel, halt, open-order parsing."""

from dataclasses import replace

from market_helpers import make_market
from world_cup_bot import order_manager
from world_cup_bot.config import Settings
from world_cup_bot.quoter import MarketSnapshot, QuoteIntent


def _settings(**overrides) -> Settings:
    base = Settings.from_env()
    return replace(base, **overrides) if overrides else base


def test_open_order_from_clob_row_filters_matched():
    row = {
        "id": "ord-1",
        "asset_id": "tok-yes",
        "market": "0xcond",
        "status": "MATCHED",
        "price": "0.45",
        "original_size": "100",
        "size_matched": "100",
        "side": "BUY",
    }
    assert order_manager.OpenOrder.from_clob_row(row) is None


def test_open_order_from_clob_row_live():
    row = {
        "id": "ord-2",
        "asset_id": "tok-yes",
        "market": "0xcond",
        "status": "LIVE",
        "price": "0.45",
        "original_size": "100",
        "size_matched": "0",
        "side": "BUY",
    }
    parsed = order_manager.OpenOrder.from_clob_row(row, team_by_asset={"tok-yes": "Turkey"})
    assert parsed is not None
    assert parsed.order_id == "ord-2"
    assert parsed.team == "Turkey"
    assert parsed.size == 100.0


def test_trading_halt_blocks_team():
    halt = order_manager.TradingHalt()
    assert not halt.is_halted("Turkey")
    halt.halt_team("Turkey", "test")
    assert halt.is_halted("Turkey")
    assert not halt.is_halted("Mexico")


def test_fetch_wc_open_orders_requires_auth(monkeypatch):
    import pytest

    from world_cup_bot.clob_auth import MissingClobAuthError

    def boom():
        raise MissingClobAuthError("no creds")

    monkeypatch.setattr(order_manager, "load_clob_auth", boom)
    market = make_market("Turkey", mid=0.45)
    overrides = {
        **market.__dict__,
        "yes_token_id": "yes-tok",
        "no_token_id": "no-tok",
        "condition_id": "0x1",
    }
    market = market.__class__(**overrides)
    with pytest.raises(MissingClobAuthError):
        order_manager.fetch_wc_open_orders(_settings(dry_run=False), [market])
    assert order_manager.fetch_wc_open_orders(_settings(dry_run=True), [market]) == []


def test_cancel_orders_dry_run(monkeypatch):
    settings = _settings(dry_run=True)
    market = make_market("Turkey", mid=0.45, hours_to_kickoff=6.0)
    market = market.__class__(
        **{
            **market.__dict__,
            "yes_token_id": "yes-tok",
            "no_token_id": "no-tok",
            "condition_id": "0x1",
        }
    )
    open_order = order_manager.OpenOrder(
        order_id="live-1",
        asset_id="yes-tok",
        condition_id="0x1",
        side="BUY",
        price=0.44,
        size=500.0,
        status="LIVE",
        team="Turkey",
    )
    monkeypatch.setattr(
        order_manager,
        "fetch_wc_open_orders",
        lambda *a, **k: [open_order],
    )
    called: list[list[str]] = []

    def fake_cancel(settings, order_ids, *, dry_run):
        called.append(order_ids)
        return order_ids

    monkeypatch.setattr(order_manager, "_cancel_order_ids", fake_cancel)

    result = order_manager.cancel_for_teams(
        settings,
        [market],
        {"Turkey"},
        reason="test",
    )
    assert result.order_ids == ["live-1"]
    assert called == [["live-1"]]


def test_apply_fill_safety_kill_switch_halt_and_cancel(monkeypatch):
    settings = _settings(dry_run=True)
    market = make_market("Turkey", mid=0.45, hours_to_kickoff=6.0)
    halt = order_manager.TradingHalt()
    cancel_calls: list[str] = []

    def fake_cancel_for_teams(*args, **kwargs):
        cancel_calls.append(kwargs.get("reason", ""))
        return order_manager.CancelResult(
            order_ids=["x"],
            dry_run=True,
            reason="ok",
            teams=("Turkey",),
        )

    monkeypatch.setattr(order_manager, "cancel_for_teams", fake_cancel_for_teams)

    order_manager.apply_fill_safety_actions(
        settings,
        [market],
        team="Turkey",
        kill_switch=True,
        pull_quotes=True,
        halt=halt,
    )
    assert halt.is_halted("Turkey")
    assert cancel_calls


def test_cancel_replace_before_submit(monkeypatch):
    settings = _settings(dry_run=True)
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{
            **market.__dict__,
            "yes_token_id": "yes-tok",
            "no_token_id": "no-tok",
            "condition_id": "0x1",
        }
    )
    stale = order_manager.OpenOrder(
        order_id="old-1",
        asset_id="yes-tok",
        condition_id="0x1",
        side="BUY",
        price=0.40,
        size=500.0,
        status="LIVE",
        team="Turkey",
    )
    monkeypatch.setattr(order_manager, "fetch_wc_open_orders", lambda *a, **k: [stale])

    cancelled: list[list[str]] = []

    def fake_cancel(settings, orders, *, reason, dry_run=None, **kwargs):
        cancelled.append([o.order_id for o in orders])
        return order_manager.CancelResult(
            order_ids=[o.order_id for o in orders],
            dry_run=True,
            reason=reason,
        )

    monkeypatch.setattr(order_manager, "cancel_orders", fake_cancel)

    snap = MarketSnapshot.from_market(market)
    assert snap is not None
    intent = QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="yes-tok",
        order_id="new-1",
        price=0.44,
        size_shares=500.0,
        notional_usd=220.0,
        dry_run=True,
        reason="test",
        snapshot=snap,
    )
    results = order_manager.cancel_replace_before_submit(settings, [market], [intent])
    assert len(results) == 1
    assert cancelled == [["old-1"]]
