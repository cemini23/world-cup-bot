import json
from pathlib import Path

import pytest

from market_helpers import make_market
from world_cup_bot import conviction, liquidity_scanner
from world_cup_bot.operating_config import LiquidityOps

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _liq_cfg(**overrides) -> LiquidityOps:
    defaults = dict(
        min_depth_within_reward_spread_usd=50,
        min_ask_depth_within_reward_spread_usd=15,
        min_combined_book_depth_usd=150,
        min_levels_per_side=2,
        max_spread_cents=None,
        auto_clear_human_review=True,
    )
    defaults.update(overrides)
    return LiquidityOps(**defaults)


def _sample_book() -> dict:
    with (FIXTURES / "clob_book_sample.json").open(encoding="utf-8") as f:
        return json.load(f)


def test_ahead_bid_notional_usd():
    book = {
        "bids": [
            {"price": "0.88", "size": "100"},
            {"price": "0.85", "size": "200"},
            {"price": "0.84", "size": "300"},
        ],
        "asks": [],
    }
    ahead = liquidity_scanner.ahead_bid_notional_usd(book, 0.84)
    assert ahead == pytest.approx(0.88 * 100 + 0.85 * 200)


def test_depth_in_band_bids_only_inside_range():
    levels = [(0.84, 500.0), (0.70, 1000.0)]
    depth = liquidity_scanner._depth_in_band(levels, side="bid", mid=0.86, half_spread=0.045)
    assert depth == 0.84 * 500.0
    assert 0.70 not in [p for p, _ in levels if p >= 0.815]


def test_token_depth_from_fixture():
    book = _sample_book()
    tok = liquidity_scanner._token_depth(
        book, token_id="yes", label="YES", mid=0.86, half_spread=0.045
    )
    assert tok.bid.levels == 3
    assert tok.ask.levels == 3
    assert tok.bid.depth_in_band_usd > 300
    assert tok.ask.depth_in_band_usd > 300


def test_evaluate_liquidity_gate_pass():
    book = _sample_book()
    tok = liquidity_scanner._token_depth(
        book, token_id="yes", label="YES", mid=0.86, half_spread=0.045
    )
    cfg = _liq_cfg()
    ok, reasons = liquidity_scanner.evaluate_liquidity_gate(
        yes=tok, no=None, cfg=cfg, bilateral=False
    )
    assert ok
    assert "pass" in reasons[0]


def test_evaluate_liquidity_gate_pass_thin_ask():
    """Ask band can pass at $15 floor while bid still requires $50."""
    book = {
        "bids": [
            {"price": "0.85", "size": "120"},
            {"price": "0.84", "size": "80"},
        ],
        "asks": [
            {"price": "0.87", "size": "22"},
            {"price": "0.88", "size": "10"},
        ],
    }
    tok = liquidity_scanner._token_depth(
        book, token_id="yes", label="YES", mid=0.86, half_spread=0.045
    )
    assert tok.bid.depth_in_band_usd >= 50
    assert 15 <= tok.ask.depth_in_band_usd < 50
    cfg = _liq_cfg()
    ok, reasons = liquidity_scanner.evaluate_liquidity_gate(
        yes=tok, no=None, cfg=cfg, bilateral=False
    )
    assert ok
    assert "pass" in reasons[0]


def test_evaluate_liquidity_gate_fail_ask_below_floor():
    book = {
        "bids": [
            {"price": "0.85", "size": "120"},
            {"price": "0.84", "size": "80"},
        ],
        "asks": [{"price": "0.87", "size": "10"}],
    }
    tok = liquidity_scanner._token_depth(
        book, token_id="yes", label="YES", mid=0.86, half_spread=0.045
    )
    cfg = _liq_cfg()
    ok, reasons = liquidity_scanner.evaluate_liquidity_gate(
        yes=tok, no=None, cfg=cfg, bilateral=False
    )
    assert not ok
    assert any("ask band depth" in r for r in reasons)


def test_evaluate_liquidity_gate_fail_levels():
    book = {"bids": [{"price": "0.85", "size": "1000"}], "asks": []}
    tok = liquidity_scanner._token_depth(
        book, token_id="yes", label="YES", mid=0.86, half_spread=0.045
    )
    cfg = _liq_cfg(
        min_depth_within_reward_spread_usd=100,
        min_combined_book_depth_usd=100,
        min_levels_per_side=2,
        auto_clear_human_review=False,
    )
    ok, reasons = liquidity_scanner.evaluate_liquidity_gate(
        yes=tok, no=None, cfg=cfg, bilateral=False
    )
    assert not ok
    assert any("levels" in r for r in reasons)


def test_scan_market_liquidity_mocked(monkeypatch):
    book = _sample_book()
    monkeypatch.setattr(
        "world_cup_bot.liquidity_scanner.fetch_book",
        lambda _url, _tid: book,
    )
    m = make_market("Morocco", mid=0.86)
    cfg = _liq_cfg()
    report = liquidity_scanner.scan_market_liquidity(
        m, clob_url="https://clob.polymarket.com", cfg=cfg
    )
    assert report.passes
    assert report.yes is not None
    assert report.no is None


def test_human_review_cleared_when_liquidity_passes(monkeypatch):
    book = {
        "bids": [
            {"price": "0.43", "size": "800"},
            {"price": "0.42", "size": "600"},
        ],
        "asks": [
            {"price": "0.47", "size": "700"},
            {"price": "0.48", "size": "500"},
        ],
    }
    monkeypatch.setattr(
        "world_cup_bot.liquidity_scanner.fetch_book",
        lambda _url, _tid: book,
    )
    cfg_conv = conviction.load_conviction_config()
    m = make_market("Morocco", mid=0.45)
    liq_cfg = _liq_cfg()
    report = liquidity_scanner.scan_market_liquidity(
        m, clob_url="https://clob.polymarket.com", cfg=liq_cfg
    )
    result = conviction.evaluate_market(
        m,
        cfg_conv,
        liquidity=report,
        liquidity_cfg=liq_cfg,
        liquidity_gate=True,
    )
    assert result.quote
    assert "cleared by CLOB depth" in result.reason


def test_human_review_liquidity_pass_but_mid_blocked():
    cfg_conv = conviction.load_conviction_config()
    m = make_market("Morocco", mid=0.865)
    liq_cfg = _liq_cfg(
        min_depth_within_reward_spread_usd=100,
        min_combined_book_depth_usd=100,
        min_levels_per_side=1,
    )
    book = _sample_book()
    tok = liquidity_scanner._token_depth(
        book, token_id="yes", label="YES", mid=0.865, half_spread=0.045
    )
    from world_cup_bot.liquidity_scanner import LiquidityReport

    report = LiquidityReport(
        market=m,
        midpoint=0.865,
        half_spread=0.045,
        yes=tok,
        no=None,
        fetch_errors=(),
        passes=True,
        reasons=("liquidity gate pass",),
    )
    result = conviction.evaluate_market(
        m,
        cfg_conv,
        liquidity=report,
        liquidity_cfg=liq_cfg,
        liquidity_gate=True,
    )
    assert not result.quote
    assert "liquidity PASS but tier blocked" in result.reason
