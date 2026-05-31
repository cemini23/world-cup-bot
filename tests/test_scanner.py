import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_helpers import make_market
from world_cup_bot import scanner

FIXTURE = Path(__file__).parent / "fixtures" / "gamma_search_sample.json"


def _opener(_url: str, timeout: int = 30):
    return io.BytesIO(FIXTURE.read_bytes())


def test_parse_team_from_question():
    assert (
        scanner.parse_team_from_question(
            "Will Turkey advance to the knockout stages at the 2026 FIFA World Cup?"
        )
        == "Turkey"
    )


def test_discover_from_fixture():
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    markets = scanner.discover_advance_markets(
        "https://gamma-api.polymarket.com",
        now=now,
        opener=_opener,
    )
    assert len(markets) == 2
    mexico = next(m for m in markets if m.team == "Mexico")
    assert mexico.mid == pytest.approx(0.83)
    assert not mexico.bilateral_mode
    assert mexico.lp_eligible
    assert mexico.rewards_params_ok
    assert mexico.kickoff_known


def test_bilateral_mode_high_mid():
    market = {
        "question": "Will Spain advance to the knockout stages at the 2026 FIFA World Cup?",
        "slug": "spain",
        "conditionId": "0x1",
        "clobTokenIds": ["1", "2"],
        "bestBid": 0.92,
        "bestAsk": 0.94,
        "rewardsMinSize": 500,
        "rewardsMaxSpread": 4.5,
        "acceptingOrders": True,
    }
    now = datetime(2026, 6, 1, tzinfo=UTC)
    parsed = scanner.parse_market(market, now=now)
    assert parsed is not None
    assert parsed.bilateral_mode


def test_bilateral_mode_exact_high_threshold():
    """Mid exactly at high_mid must set bilateral_mode (align with conviction >=)."""
    market = {
        "question": "Will France advance to the knockout stages at the 2026 FIFA World Cup?",
        "slug": "france",
        "conditionId": "0x2",
        "clobTokenIds": ["1", "2"],
        "bestBid": 0.89,
        "bestAsk": 0.91,
        "rewardsMinSize": 500,
        "rewardsMaxSpread": 4.5,
        "acceptingOrders": True,
    }
    now = datetime(2026, 6, 1, tzinfo=UTC)
    parsed = scanner.parse_market(market, now=now)
    assert parsed is not None
    assert parsed.mid == pytest.approx(0.90)
    assert parsed.bilateral_mode


def test_lp_eligible_fail_closed_unknown_kickoff():
    m = make_market("Unknown FC", mid=0.45, hours_to_kickoff=None)
    assert not m.kickoff_known
    assert not m.lp_eligible


def test_lp_eligible_fail_closed_missing_rewards():
    m = make_market("Turkey", mid=0.45, rewards_min_shares=None)
    assert not m.rewards_params_ok
    assert not m.lp_eligible


def test_lp_eligible_respects_min_hours_config():
    m = make_market("Turkey", mid=0.45, hours_to_kickoff=8.0, min_hours=10.0)
    assert m.must_cancel
    assert not m.lp_eligible

    m2 = make_market("Turkey", mid=0.45, hours_to_kickoff=12.0, min_hours=10.0)
    assert m2.lp_eligible
