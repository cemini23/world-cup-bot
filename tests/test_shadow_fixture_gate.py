"""CI gate: shadow Phase 1 passes with fixture ledger (offline)."""

from pathlib import Path

from world_cup_bot.config import Settings
from world_cup_bot.preflight import CheckStatus, PreflightCheck, PreflightReport
from world_cup_bot.shadow_checklist import StepStatus, build_shadow_steps

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "shadow_phase1_ledger.jsonl"


def _settings() -> Settings:
    return Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://example/ws/user",
        ws_market_url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
        data_api_url="https://data-api.polymarket.com",
        match_shock_tape_dir="data/local/shock_tapes",
        match_shock_ledger_path="data/local/match_shock_paper.jsonl",
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path=str(FIXTURE),
        operating_config="config/operating.yaml",
        cross_venue_config="config/cross_venue.yaml",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
        market_phases_config="config/market_phases.yaml",
    )


def _fake_preflight(*_args, **_kwargs) -> PreflightReport:
    return PreflightReport(
        checks=[
            PreflightCheck("gamma", CheckStatus.PASS, "Gamma OK"),
            PreflightCheck("geoblock", CheckStatus.WARN, "US shadow WARN"),
            PreflightCheck("l2_creds", CheckStatus.SKIP, "skipped"),
        ],
        ok=True,
    )


def test_shadow_phase1_fixture_gate(monkeypatch):
    monkeypatch.setattr("world_cup_bot.shadow_checklist.run_preflight", _fake_preflight)
    steps = build_shadow_steps(_settings(), test_auth=False)
    by_id = {s.id: s for s in steps}

    assert by_id["dry_plan"].status == StepStatus.DONE
    assert "3 day" in by_id["dry_plan"].detail

    min_phase = 1
    for step in steps:
        if step.phase > min_phase:
            continue
        assert step.status not in {StepStatus.BLOCKED, StepStatus.PENDING}, (
            f"phase {step.phase} step {step.id} is {step.status}"
        )
