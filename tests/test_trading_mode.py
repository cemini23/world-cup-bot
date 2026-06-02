"""Tests for unified LP / shock mode handoff."""

from __future__ import annotations

import pytest

from world_cup_bot.trading_mode import (
    MarketKind,
    ModeHandoffConfig,
    TradingMode,
    infer_market_kind_from_slug,
    resolve_trading_mode,
)


@pytest.fixture
def cfg():
    return ModeHandoffConfig(
        min_hours_before_kickoff=10.0,
        max_match_hours=2.0,
        shock_enabled=True,
    )


def test_advance_lp_before_cancel_window(cfg):
    d = resolve_trading_mode(
        market_kind=MarketKind.ADVANCE,
        hours_to_kickoff=24.0,
        cfg=cfg,
    )
    assert d.mode == TradingMode.LP
    assert d.lp_active


def test_advance_off_inside_cancel_window(cfg):
    d = resolve_trading_mode(
        market_kind=MarketKind.ADVANCE,
        hours_to_kickoff=6.0,
        cfg=cfg,
    )
    assert d.mode == TradingMode.OFF
    assert d.reason == "cancel_window_or_live"


def test_match_off_pregame(cfg):
    d = resolve_trading_mode(
        market_kind=MarketKind.MATCH,
        hours_to_kickoff=3.0,
        cfg=cfg,
    )
    assert d.mode == TradingMode.OFF
    assert d.reason == "pregame_no_shock"


def test_match_shock_in_play(cfg):
    d = resolve_trading_mode(
        market_kind=MarketKind.MATCH,
        hours_to_kickoff=-0.5,
        cfg=cfg,
    )
    assert d.mode == TradingMode.SHOCK
    assert d.shock_active


def test_match_off_post_match(cfg):
    d = resolve_trading_mode(
        market_kind=MarketKind.MATCH,
        hours_to_kickoff=-2.5,
        cfg=cfg,
    )
    assert d.mode == TradingMode.OFF
    assert d.reason == "post_match"


def test_shock_disabled(cfg):
    off_cfg = ModeHandoffConfig(
        min_hours_before_kickoff=10.0,
        shock_enabled=False,
    )
    d = resolve_trading_mode(
        market_kind=MarketKind.MATCH,
        hours_to_kickoff=-0.25,
        cfg=off_cfg,
    )
    assert d.mode == TradingMode.OFF


def test_infer_market_kind():
    assert infer_market_kind_from_slug("will-brazil-advance-to-knockout") == MarketKind.ADVANCE
    assert infer_market_kind_from_slug("fifa-world-cup-usa-vs-mexico") == MarketKind.MATCH
