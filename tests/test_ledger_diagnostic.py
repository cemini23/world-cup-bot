"""Ledger diagnostics for shadow plan audits."""

from __future__ import annotations

import json
from pathlib import Path

from world_cup_bot.ledger import record_diagnostic, summarize_pnl
from world_cup_bot.logic_version import PnlScope, load_strategy_version


def test_record_diagnostic_negative_filter_summary(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    spec = load_strategy_version()
    record_diagnostic(
        spec,
        path=ledger,
        event="negative_filter_summary",
        fields={"market_count": 48, "quoted": 16, "yaml_skip": 13},
    )
    rows = [json.loads(ln) for ln in ledger.read_text().splitlines()]
    assert rows[0]["event"] == "negative_filter_summary"
    assert rows[0]["quoted"] == 16


def test_summarize_pnl_realized_pnl_alias(tmp_path: Path):
    spec = load_strategy_version()
    rows = [
        {
            "event": "order_fill",
            "logic_version": spec.version_id,
            "realized_pnl_usd": 1.25,
        }
    ]
    summary = summarize_pnl(rows, spec, PnlScope.ALL)
    assert summary.realized_pnl_usd == 1.25
