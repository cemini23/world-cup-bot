"""Tests for preflight checks."""

from world_cup_bot.clob_rest import ClobBurstProbe, GeoblockStatus
from world_cup_bot.config import Settings
from world_cup_bot.preflight import CheckStatus, run_preflight


def test_preflight_dry_run_warns(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("POLYMARKET_API_KEY", raising=False)

    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_geoblock",
        lambda: GeoblockStatus(blocked=False, ip="1.2.3.4", country="FI", region=""),
    )
    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_search_payload",
        lambda *_a, **_k: {"events": [{"id": 1}]},
    )
    monkeypatch.setattr("world_cup_bot.preflight.fetch_clob_time", lambda *_a, **_k: 1700000000)
    monkeypatch.setattr(
        "world_cup_bot.preflight.probe_clob_burst",
        lambda *_a, **_k: ClobBurstProbe(5, 5, 0, {}),
    )

    report = run_preflight(Settings.from_env(), test_auth=False)
    names = {c.name: c.status for c in report.checks}
    assert names["dry_run"] == CheckStatus.WARN
    assert names["geoblock"] == CheckStatus.PASS
    assert names["gamma"] == CheckStatus.PASS
    assert names["clob_rate_limit"] == CheckStatus.PASS


def test_preflight_geoblock_fail_when_live(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "11" * 32)

    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_geoblock",
        lambda: GeoblockStatus(blocked=True, ip="1.2.3.4", country="US", region="FL"),
    )
    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_search_payload",
        lambda *_a, **_k: {"events": []},
    )
    monkeypatch.setattr("world_cup_bot.preflight.fetch_clob_time", lambda *_a, **_k: 1700000000)
    monkeypatch.setattr(
        "world_cup_bot.preflight.probe_clob_burst",
        lambda *_a, **_k: ClobBurstProbe(5, 5, 0, {}),
    )

    report = run_preflight(Settings.from_env(), test_auth=False)
    geo = next(c for c in report.checks if c.name == "geoblock")
    assert geo.status == CheckStatus.FAIL
    assert report.ok is False
