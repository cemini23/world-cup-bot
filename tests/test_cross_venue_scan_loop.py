"""CLI loop behavior for cross-venue-scan."""

from __future__ import annotations

import argparse

import pytest

from world_cup_bot import __main__ as cli
from world_cup_bot.cross_venue_scanner import CrossVenueScanResult


def _empty_scan_result() -> CrossVenueScanResult:
    return CrossVenueScanResult(
        scanned_at="2026-01-01T00:00:00Z",
        config_version=1,
        alert_threshold_pp=5.0,
        blockers=(),
        rows=(),
        discoveries=(),
        pm_market_count=0,
        kalshi_market_count=0,
    )


def test_cross_venue_scan_loop_runs_multiple_cycles(monkeypatch):
    """--loop must continue polling even though once=True is the argparse default."""
    calls = {"n": 0}

    sleep_calls: list[float] = []

    def fake_sleep(sec: float) -> None:
        sleep_calls.append(sec)

    def fake_run_scan_interrupt_on_second(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt()
        return _empty_scan_result()

    monkeypatch.setattr(cli.cross_venue_scanner, "run_scan", fake_run_scan_interrupt_on_second)
    monkeypatch.setattr(cli, "phase_router_enabled", lambda: False)
    monkeypatch.setattr(cli.cross_venue_alerts, "notify_scan_results", lambda _r: None)
    monkeypatch.setattr("time.sleep", fake_sleep)

    args = argparse.Namespace(
        team=None,
        discover=False,
        discover_only=False,
        json=False,
        alert_only=True,
        record=False,
        notional=None,
        no_auto_exec=True,
        once=True,
        loop=True,
    )

    with pytest.raises(KeyboardInterrupt):
        cli._cmd_cross_venue_scan(args)

    assert calls["n"] == 2
    assert sleep_calls == [120]


def test_cross_venue_scan_once_exits_after_single_cycle(monkeypatch):
    calls = {"n": 0}

    def fake_run_scan(*_args, **_kwargs):
        calls["n"] += 1
        return _empty_scan_result()

    monkeypatch.setattr(cli.cross_venue_scanner, "run_scan", fake_run_scan)
    monkeypatch.setattr(cli, "phase_router_enabled", lambda: False)
    monkeypatch.setattr(cli.cross_venue_alerts, "notify_scan_results", lambda _r: None)

    args = argparse.Namespace(
        team=None,
        discover=False,
        discover_only=False,
        json=False,
        alert_only=True,
        record=False,
        notional=None,
        no_auto_exec=True,
        once=True,
        loop=False,
    )

    assert cli._cmd_cross_venue_scan(args) == 0
    assert calls["n"] == 1
