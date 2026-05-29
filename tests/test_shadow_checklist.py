"""Tests for shadow checklist progress."""

from world_cup_bot.config import Settings
from world_cup_bot.preflight import CheckStatus, PreflightCheck, PreflightReport
from world_cup_bot.shadow_checklist import StepStatus, build_shadow_steps


def _settings(**kwargs) -> Settings:
    base = {
        "gamma_url": "https://gamma-api.polymarket.com",
        "clob_url": "https://clob.polymarket.com",
        "ws_user_url": "wss://example/ws/user",
        "dry_run": True,
        "min_hours_before_kickoff": 10.0,
        "max_notional_per_market_usd": 2000.0,
        "conviction_config": "config/conviction.yaml",
        "logic_version_config": "config/strategy_logic_versions.yaml",
        "ledger_path": "data/local/test-shadow-ledger.jsonl",
        "operating_config": "config/operating.yaml",
        "cross_venue_config": "config/cross_venue.yaml",
        "kalshi_base_url": "https://api.elections.kalshi.com/trade-api/v2",
    }
    base.update(kwargs)
    return Settings(**base)


def _fake_preflight(*_args, **_kwargs) -> PreflightReport:
    return PreflightReport(
        checks=[
            PreflightCheck("gamma", CheckStatus.PASS, "Gamma OK"),
            PreflightCheck("geoblock", CheckStatus.WARN, "US shadow WARN"),
            PreflightCheck("l2_creds", CheckStatus.SKIP, "skipped"),
        ],
        ok=True,
    )


def test_build_shadow_steps_dry_run(monkeypatch):
    monkeypatch.setattr("world_cup_bot.shadow_checklist.run_preflight", _fake_preflight)
    steps = build_shadow_steps(_settings(), test_auth=False)
    assert len(steps) == 5
    assert steps[0].id == "install"
    assert steps[0].status in {StepStatus.DONE, StepStatus.WARN}
    assert steps[-1].id == "live_ready"
    assert steps[-1].status == StepStatus.BLOCKED
