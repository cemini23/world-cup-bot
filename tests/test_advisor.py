"""Tests for optional LLM advisor layer."""

from __future__ import annotations

import json
from unittest.mock import patch

from market_helpers import make_market
from world_cup_bot import advisor, conviction, quoter
from world_cup_bot.advisor import AdvisorGate, AdvisorVerdict, TeamAdvisorVerdict
from world_cup_bot.config import Settings
from world_cup_bot.conviction import load_conviction_config
from world_cup_bot.logic_version import load_strategy_version


def _settings() -> Settings:
    return Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://ws-subscriptions-clob.polymarket.com/ws/user",
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path="data/local/ledger.jsonl",
        operating_config="config/operating.yaml",
        cross_venue_config="config/cross_venue.yaml",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
    )


def _result(team: str = "Turkey", *, quote: bool = True):
    market = make_market(team, mid=0.45)
    cfg = load_conviction_config()
    ev = conviction.evaluate_market(market, cfg)
    if quote:
        return ev
    return conviction.ConvictionResult(market, ev.mode, False, "forced skip")


def test_parse_advisor_response_array():
    raw = json.dumps(
        [
            {
                "team": "Turkey",
                "verdict": "reduce",
                "confidence": 0.8,
                "notional_multiplier": 0.5,
                "reasons": ["injury rumor"],
                "risk_factors": ["lineup uncertain"],
                "signal_quality": "weak",
            }
        ]
    )
    verdicts = advisor.parse_advisor_response(raw)
    assert len(verdicts) == 1
    assert verdicts[0].verdict == AdvisorVerdict.REDUCE
    assert verdicts[0].notional_multiplier == 0.5


def test_skip_forces_zero_multiplier():
    v = advisor.parse_verdict_payload(
        {
            "team": "Turkey",
            "verdict": "skip",
            "confidence": 0.9,
            "notional_multiplier": 1.0,
        }
    )
    assert v is not None
    assert v.notional_multiplier == 0.0


def test_apply_hard_gate_skips():
    results = [_result("Turkey"), _result("Colombia")]
    verdicts = [
        TeamAdvisorVerdict("Turkey", AdvisorVerdict.SKIP, 0.9, 0.0, reasons=["news"]),
    ]
    applied = advisor.apply_advisor_gates(results, verdicts, gate=AdvisorGate.HARD)
    assert len(applied.kept) == 1
    assert applied.kept[0].market.team == "Colombia"
    assert len(applied.skipped) == 1


def test_apply_soft_gate_keeps_skip_verdict_team():
    results = [_result("Turkey")]
    verdicts = [
        TeamAdvisorVerdict("Turkey", AdvisorVerdict.SKIP, 0.9, 0.0, reasons=["news"]),
    ]
    applied = advisor.apply_advisor_gates(results, verdicts, gate=AdvisorGate.SOFT)
    assert len(applied.kept) == 1


def test_build_decision_context_offline():
    cfg = load_conviction_config()
    spec = load_strategy_version()
    market = make_market("Turkey", mid=0.45)
    ctx = advisor.build_decision_context(
        markets=[market],
        conviction=cfg,
        version_spec=spec,
        dry_run=True,
        min_hours_before_kickoff=10.0,
        cancel_window=[],
        ledger_summary=None,
    )
    assert ctx.logic_version == spec.version_id
    assert len(ctx.conviction_rows) == 1
    assert ctx.conviction_rows[0]["team"] == "Turkey"


def test_noop_advisor_empty():
    cfg = load_conviction_config()
    spec = load_strategy_version()
    ctx = advisor.build_decision_context(
        markets=[make_market("Turkey", mid=0.45)],
        conviction=cfg,
        version_spec=spec,
        dry_run=True,
        min_hours_before_kickoff=10.0,
        cancel_window=[],
        ledger_summary=None,
    )
    assert advisor.NoopAdvisor().review(ctx) == []


def test_build_quotes_respects_multiplier():
    cfg = load_conviction_config()
    settings = _settings()
    result = _result("Turkey")
    full = quoter.build_quotes(result, cfg, settings, notional_multiplier=1.0)
    half = quoter.build_quotes(result, cfg, settings, notional_multiplier=0.5)
    assert full[0].notional_usd > half[0].notional_usd


def test_openai_advisor_mock():
    cfg = load_conviction_config()
    spec = load_strategy_version()
    ctx = advisor.build_decision_context(
        markets=[make_market("Turkey", mid=0.45)],
        conviction=cfg,
        version_spec=spec,
        dry_run=True,
        min_hours_before_kickoff=10.0,
        cancel_window=[],
        ledger_summary=None,
    )
    settings = advisor.AdvisorSettings(
        base_url="http://localhost:11434/v1",
        api_key=None,
        model="llama3.2",
        timeout_sec=5.0,
        prompt_path=advisor.DEFAULT_PROMPT,
    )
    response = json.dumps([{"team": "Turkey", "verdict": "quote", "confidence": 0.7}])
    with patch("world_cup_bot.advisor._post_chat", return_value=response):
        verdicts = advisor.OpenAICompatibleAdvisor(settings).review(ctx)
    assert len(verdicts) == 1
    assert verdicts[0].verdict == AdvisorVerdict.QUOTE


def test_load_advisor_not_configured():
    settings = advisor.AdvisorSettings(
        base_url=None,
        api_key=None,
        model="x",
        timeout_sec=1.0,
        prompt_path=advisor.DEFAULT_PROMPT,
    )
    try:
        advisor.load_advisor(settings)
        raised = False
    except advisor.AdvisorNotConfiguredError:
        raised = True
    assert raised
