import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

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


def test_bilateral_mode_high_mid():
    market = {
        "question": "Will Spain advance to the knockout stages at the 2026 FIFA World Cup?",
        "slug": "spain",
        "conditionId": "0x1",
        "clobTokenIds": ["1", "2"],
        "bestBid": 0.92,
        "bestAsk": 0.94,
        "acceptingOrders": True,
    }
    now = datetime(2026, 6, 1, tzinfo=UTC)
    parsed = scanner.parse_market(market, now=now)
    assert parsed is not None
    assert parsed.bilateral_mode
