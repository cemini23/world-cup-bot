"""Rewards sync — parse + ledger dedup."""

from datetime import UTC, datetime
from pathlib import Path

from market_helpers import make_market
from world_cup_bot import ledger
from world_cup_bot.logic_version import StrategyVersionSpec
from world_cup_bot.rewards_sync import parse_reward_rows, sync_rewards_for_date


def _spec() -> StrategyVersionSpec:
    return StrategyVersionSpec(
        strategy_key="pm_wc_advance_lp",
        version_id="wc_advance_lp_v4",
        deployed_at=datetime.now(UTC),
        note="test",
        legacy_version_ids=frozenset(),
    )


def test_parse_reward_rows_filters_non_wc():
    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{
            **market.__dict__,
            "condition_id": "0xabc",
            "yes_token_id": "yes",
            "no_token_id": "no",
        }
    )
    team_map = {"0xabc": "Turkey"}
    payload = [
        {
            "condition_id": "0xabc",
            "earnings": 0.5,
            "asset_rate": 1,
            "asset_address": "0x1",
            "maker_address": "0x2",
        },
        {
            "condition_id": "0xdead",
            "earnings": 9.0,
            "asset_rate": 1,
        },
    ]
    rows = parse_reward_rows(payload, earn_date="2026-05-28", team_map=team_map)
    assert len(rows) == 1
    assert rows[0].team == "Turkey"
    assert rows[0].rewards_usd == 0.5
    assert rows[0].reward_key == "2026-05-28:0xabc"


def test_sync_rewards_for_date_records_and_dedups(monkeypatch, tmp_path: Path):
    from dataclasses import replace

    from world_cup_bot.config import Settings

    market = make_market("Turkey", mid=0.45)
    market = market.__class__(
        **{
            **market.__dict__,
            "condition_id": "0xabc",
            "yes_token_id": "yes",
            "no_token_id": "no",
        }
    )
    settings = replace(Settings.from_env(), ledger_path=str(tmp_path / "l.jsonl"))
    spec = _spec()

    monkeypatch.setattr(
        "world_cup_bot.rewards_sync.fetch_user_rewards_for_date",
        lambda *a, **k: [
            {
                "condition_id": "0xabc",
                "earnings": 1.25,
                "asset_rate": 1,
                "asset_address": "0x1",
                "maker_address": "0x2",
            }
        ],
    )
    monkeypatch.setattr("world_cup_bot.rewards_sync.load_clob_auth", lambda: object())
    monkeypatch.setattr("world_cup_bot.rewards_sync.load_poly_address", lambda: "0xsigner")
    monkeypatch.setattr("world_cup_bot.rewards_sync.load_maker_address", lambda: "0xmaker")

    first = sync_rewards_for_date(
        settings,
        [market],
        spec,
        earn_date="2026-05-28",
        record=True,
    )
    second = sync_rewards_for_date(
        settings,
        [market],
        spec,
        earn_date="2026-05-28",
        record=True,
    )
    assert first.recorded == 1
    assert second.recorded == 0
    assert second.skipped_existing == 1
    rows = ledger.load_rows(Path(settings.ledger_path))
    assert len(rows) == 1
    assert rows[0]["event"] == "reward_accrual"
    assert rows[0]["rewards_usd"] == 1.25
