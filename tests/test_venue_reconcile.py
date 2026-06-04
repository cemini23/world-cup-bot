"""Compare venue export order ids to ledger fills."""

from __future__ import annotations

from pathlib import Path

from world_cup_bot.venue_reconcile import (
    _maker_order_ids_from_trades,
    compare_venue_csv,
    compare_venue_sets,
    load_venue_order_ids,
)


def test_load_venue_order_ids(tmp_path: Path):
    csv_path = tmp_path / "pm.csv"
    csv_path.write_text(
        "order_id,team,side\n0xaaa,USA,YES\n0xbbb,Spain,YES\n",
        encoding="utf-8",
    )
    ids, col = load_venue_order_ids(csv_path)
    assert col == "order_id"
    assert ids == ("0xaaa", "0xbbb")


def test_compare_venue_csv_matched_and_gaps(tmp_path: Path):
    csv_path = tmp_path / "pm.csv"
    csv_path.write_text("order_id\n0xaaa\n0xccc\n", encoding="utf-8")
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(
        '{"event":"order_fill","order_id":"0xaaa","logic_version":"wc_advance_lp_v4"}\n'
        '{"event":"order_fill","order_id":"0xbbb","logic_version":"wc_advance_lp_v4"}\n',
        encoding="utf-8",
    )
    report = compare_venue_csv(csv_path, ledger_path)
    assert report.matched == 1
    assert report.ledger_only == ("0xbbb",)
    assert report.venue_only == ("0xccc",)


def test_maker_order_ids_from_trades():
    trades = [
        {
            "status": "MATCHED",
            "market": "0xcond",
            "id": "t1",
            "maker_orders": [
                {"order_id": "0xaaa", "asset_id": "y", "price": "0.5", "matched_amount": "10"},
            ],
        },
        {"status": "CANCELLED", "id": "t2"},
    ]
    ids = _maker_order_ids_from_trades(trades)
    assert ids == {"0xaaa"}


def test_compare_venue_sets():
    report = compare_venue_sets({"0xaaa", "0xbbb"}, {"0xaaa", "0xccc"})
    assert report.matched == 1
    assert report.ledger_only == ("0xbbb",)
    assert report.venue_only == ("0xccc",)


def test_summarize_skip_buckets():
    from world_cup_bot.conviction import ConvictionResult, TeamMode, summarize_skip_buckets
    from world_cup_bot.scanner import AdvanceMarket

    m = AdvanceMarket(
        team="Test",
        question="Will Test advance?",
        slug="test",
        condition_id="c",
        yes_token_id="y",
        no_token_id="n",
        best_bid=0.48,
        best_ask=0.52,
        spread=0.04,
        mid=0.5,
        rewards_min_shares=50,
        rewards_max_spread=3,
        liquidity=1000,
        volume=5000,
        accepting_orders=True,
        hours_to_kickoff=72,
        must_cancel=False,
        bilateral_mode=False,
        min_hours_before_kickoff=2,
        prefer_hours_before_kickoff=24,
    )
    results = [
        ConvictionResult(m, TeamMode.YES_HEAVY, True, "ok"),
        ConvictionResult(m, TeamMode.SKIP, False, "per_team mode=skip"),
        ConvictionResult(m, TeamMode.HUMAN_REVIEW, False, "human_review — operator gate"),
    ]
    summary = summarize_skip_buckets(results)
    assert summary["quoted"] == 1
    assert summary["yaml_skip"] == 1
    assert summary["human_review"] == 1
