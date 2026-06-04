"""Wiki enforcement hook tests."""

import pytest

from market_helpers import make_market
from world_cup_bot.config import Settings
from world_cup_bot.operating_config import load_operating_config
from world_cup_bot.quoter import MarketSnapshot, QuoteIntent
from world_cup_bot.wiki_enforcement import WikiEnforcementError, check_intents, enforce_or_raise


def _settings() -> Settings:
    return Settings.from_env()


def test_wiki_enforcement_off_by_default():
    operating = load_operating_config()
    intent = QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="yes-Turkey",
        order_id="x",
        price=0.45,
        size_shares=100.0,
        notional_usd=5000.0,
        dry_run=False,
        reason="test",
        snapshot=None,
    )
    assert check_intents([intent], _settings(), [make_market("Turkey", mid=0.45)], operating) == []


def test_wiki_enforcement_blocks_over_cap(monkeypatch):
    monkeypatch.setenv("WC_WIKI_ENFORCEMENT", "1")
    operating = load_operating_config()
    intent = QuoteIntent(
        team="Turkey",
        side="YES",
        token_id="yes-Turkey",
        order_id="x",
        price=0.45,
        size_shares=10000.0,
        notional_usd=5000.0,
        dry_run=False,
        reason="test",
        snapshot=None,
    )
    violations = check_intents([intent], _settings(), [make_market("Turkey", mid=0.45)], operating)
    assert violations
    with pytest.raises(WikiEnforcementError):
        enforce_or_raise([intent], _settings(), [make_market("Turkey", mid=0.45)], operating)


def test_wiki_enforcement_requires_no_leg_at_high_mid(monkeypatch):
    monkeypatch.setenv("WC_WIKI_ENFORCEMENT", "1")
    operating = load_operating_config()
    snap = MarketSnapshot.from_market(make_market("France", mid=0.95))
    yes_only = QuoteIntent(
        team="France",
        side="YES",
        token_id="yes-France",
        order_id="x",
        price=0.94,
        size_shares=100.0,
        notional_usd=94.0,
        dry_run=False,
        reason="test",
        snapshot=snap,
    )
    violations = check_intents(
        [yes_only], _settings(), [make_market("France", mid=0.95)], operating
    )
    assert any("NO leg" in v for v in violations)
