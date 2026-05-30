import json
from pathlib import Path

import pytest

from market_helpers import make_market
from world_cup_bot import conviction_staleness
from world_cup_bot.ledger import LedgerRow, append_row


def test_last_quote_mid_by_team(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    append_row(
        path,
        LedgerRow(
            event="quote_intent",
            logic_version="v1",
            strategy_key="wc",
            timestamp="2026-05-28T12:00:00+00:00",
            team="Turkey",
            extra={"mid_at_place": 0.42},
        ),
    )
    append_row(
        path,
        LedgerRow(
            event="quote_intent",
            logic_version="v1",
            strategy_key="wc",
            timestamp="2026-05-29T12:00:00+00:00",
            team="Turkey",
            extra={"mid_at_place": 0.45},
        ),
    )
    mids = conviction_staleness.last_quote_mid_by_team(path)
    assert mids["Turkey"] == 0.45


def test_scan_mid_staleness_alerts(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    row = {
        "event": "quote_intent",
        "team": "Morocco",
        "mid_at_place": 0.55,
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    markets = [make_market("Morocco", mid=0.72)]
    alerts = conviction_staleness.scan_mid_staleness(
        markets,
        ledger_path=path,
        threshold_pp=15.0,
    )
    assert len(alerts) == 1
    assert alerts[0].delta_pp == pytest.approx(17.0)


def test_scan_mid_staleness_quiet(tmp_path: Path):
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        json.dumps({"event": "quote_intent", "team": "Morocco", "mid_at_place": 0.55}) + "\n",
        encoding="utf-8",
    )
    markets = [make_market("Morocco", mid=0.58)]
    alerts = conviction_staleness.scan_mid_staleness(
        markets,
        ledger_path=path,
        threshold_pp=15.0,
    )
    assert alerts == []
