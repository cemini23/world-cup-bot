"""Dry-run open-order fetch without L2 creds."""

from market_helpers import make_market
from world_cup_bot import order_manager
from world_cup_bot.config import Settings


def test_fetch_open_orders_empty_without_l2_in_dry_run(monkeypatch):
    monkeypatch.delenv("POLYMARKET_API_KEY", raising=False)
    monkeypatch.delenv("POLYMARKET_API_SECRET", raising=False)
    monkeypatch.delenv("POLYMARKET_API_PASSPHRASE", raising=False)
    settings = Settings.from_env()
    assert settings.dry_run is True
    market = make_market("Turkey", mid=0.45)
    orders = order_manager.fetch_wc_open_orders(settings, [market])
    assert orders == []
