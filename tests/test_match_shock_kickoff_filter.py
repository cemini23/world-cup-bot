from world_cup_bot.match_market_discovery import MatchMarket, filter_markets_by_slug_prefix
from world_cup_bot.match_shock_config import load_match_shock_config
from world_cup_bot.shock_tape import (
    TICK_PRICE_SANE_MAX,
    TICK_PRICE_SANE_MIN,
    ParsedTick,
    scan_shocks,
)

_SLUG = "fifwc-can-bih-2026-06-12-can"
_OUTRIGHT = "will-spain-win-the-2026-fifa-world-cup"


def test_filter_markets_by_slug_prefix():
    markets = [
        MatchMarket(_SLUG, "q", "c1", "y1", "n1", "ev", "q", True),
        MatchMarket(_OUTRIGHT, "q", "c2", "y2", "n2", "ev", "q", True),
    ]
    out = filter_markets_by_slug_prefix(markets, "fifwc-can-bih")
    assert len(out) == 1
    assert out[0].slug.startswith("fifwc-can-bih")


def test_scan_shocks_skips_stale_0999_ticks():
    cfg = load_match_shock_config()
    ticks = [
        ParsedTick(1000, 0.999, _SLUG, 0, 0, ()),
        ParsedTick(2000, 0.55, _SLUG, 0, 0, ()),
        ParsedTick(3000, 0.40, _SLUG, 0, 0, ()),
    ]
    shocks = scan_shocks(ticks, cfg)
    assert shocks == [] or all(s[1].pre_price <= TICK_PRICE_SANE_MAX for s in shocks)
    assert TICK_PRICE_SANE_MIN < TICK_PRICE_SANE_MAX
