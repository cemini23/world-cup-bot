"""Tests for preflight checks."""

import pytest

from world_cup_bot.clob_auth import ClobAuth
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


def test_preflight_geoblock_pass_when_blocked_but_clob_auth_ok_in_shadow(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "11" * 32)
    monkeypatch.setenv("POLYMARKET_POLY_ADDRESS", "0x" + "22" * 20)

    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_geoblock",
        lambda: GeoblockStatus(blocked=True, ip="203.0.113.50", country="DE", region=""),
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
    monkeypatch.setattr(
        "world_cup_bot.preflight.load_clob_auth",
        lambda: ClobAuth("k", "s", "p"),
    )
    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_open_orders",
        lambda *_a, **_k: [],
    )

    report = run_preflight(Settings.from_env(), test_auth=True)
    geo = next(c for c in report.checks if c.name == "geoblock")
    assert geo.status == CheckStatus.PASS
    assert "egress-safe" in geo.detail
    assert report.ok is True


def test_preflight_geoblock_warn_when_blocked_but_clob_auth_ok(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "11" * 32)
    monkeypatch.setenv("POLYMARKET_POLY_ADDRESS", "0x" + "22" * 20)

    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_geoblock",
        lambda: GeoblockStatus(blocked=True, ip="203.0.113.50", country="DE", region=""),
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
    monkeypatch.setattr(
        "world_cup_bot.preflight.load_clob_auth",
        lambda: ClobAuth("k", "s", "p"),
    )
    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_open_orders",
        lambda *_a, **_k: [],
    )

    report = run_preflight(Settings.from_env(), test_auth=True)
    geo = next(c for c in report.checks if c.name == "geoblock")
    assert geo.status == CheckStatus.WARN
    assert report.ok is True


def test_preflight_live_requires_clob_v2(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "11" * 32)

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
    assert names.get("py_clob_client_v2") == CheckStatus.PASS


def test_assert_live_post_allowed_skips_in_dry_run(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    from world_cup_bot.preflight import assert_live_post_allowed

    assert_live_post_allowed(Settings.from_env())


def test_assert_live_post_allowed_blocks_geoblock(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "11" * 32)

    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_geoblock",
        lambda: GeoblockStatus(blocked=True, ip="1.2.3.4", country="US", region="FL"),
    )

    from world_cup_bot.preflight import assert_live_post_allowed

    with pytest.raises(RuntimeError, match="geoblock"):
        assert_live_post_allowed(Settings.from_env())


def test_assert_live_post_allowed_blocks_preflight_fail(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0x" + "11" * 32)

    monkeypatch.setattr(
        "world_cup_bot.preflight.fetch_geoblock",
        lambda: GeoblockStatus(blocked=False, ip="1.2.3.4", country="FI", region=""),
    )
    monkeypatch.setattr(
        "world_cup_bot.preflight.run_preflight",
        lambda *_a, **_k: type(
            "R",
            (),
            {
                "checks": [
                    type("C", (), {"name": "gamma", "status": CheckStatus.FAIL, "detail": "down"})()
                ],
                "ok": False,
            },
        )(),
    )

    from world_cup_bot.preflight import assert_live_post_allowed

    with pytest.raises(RuntimeError, match="preflight FAIL"):
        assert_live_post_allowed(Settings.from_env())
