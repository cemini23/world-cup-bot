"""Tests for tournament_ops bundled health check."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from world_cup_bot.config import Settings
from world_cup_bot.fixture_watch import FixtureCheckResult
from world_cup_bot.tournament_ops import (
    CheckStatus,
    TournamentCheck,
    exit_code_for_result,
    run_tournament_ops_check,
    _check_match_shock_readiness,
)


@pytest.fixture
def settings(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    return Settings(
        gamma_url="https://gamma-api.polymarket.com",
        clob_url="https://clob.polymarket.com",
        ws_user_url="wss://example/ws/user",
        ws_market_url="wss://example/ws/market",
        data_api_url="https://data-api.polymarket.com",
        match_shock_tape_dir=str(tmp_path / "tapes"),
        match_shock_ledger_path=str(tmp_path / "shock.jsonl"),
        dry_run=True,
        min_hours_before_kickoff=10.0,
        max_notional_per_market_usd=2000.0,
        conviction_config="config/conviction.yaml",
        logic_version_config="config/strategy_logic_versions.yaml",
        ledger_path=str(ledger),
        operating_config="config/operating.yaml",
        cross_venue_config="config/cross_venue.yaml",
        kalshi_base_url="https://api.elections.kalshi.com/trade-api/v2",
        market_phases_config="config/market_phases.yaml",
    )


def test_tournament_ops_all_pass(settings):
    fixture_ok = FixtureCheckResult(
        local_path=settings.ledger_path,
        upstream_url="https://example.com/fixtures.json",
        local_sha256="abc",
        upstream_sha256="abc",
        local_match_count=104,
        upstream_match_count=104,
        changes=(),
        checked_at="2026-06-01T00:00:00Z",
    )
    shock_pass = MagicMock(
        id="match_shock_readiness",
        title="Match-shock readiness (Module 8)",
        status=CheckStatus.PASS,
        detail="ok",
        data=None,
    )
    with (
        patch("world_cup_bot.tournament_ops.check_fixtures", return_value=fixture_ok),
        patch("world_cup_bot.tournament_ops.discover_markets", return_value=[]),
        patch("world_cup_bot.tournament_ops.scan_mid_staleness", return_value=[]),
        patch("world_cup_bot.tournament_ops.cross_venue_scanner.run_scan") as mock_scan,
        patch(
            "world_cup_bot.tournament_ops._check_match_shock_readiness",
            return_value=shock_pass,
        ),
    ):
        mock_scan.return_value = MagicMock(discoveries=[])
        result = run_tournament_ops_check(settings)
    assert result.ok
    assert all(c.status == CheckStatus.PASS for c in result.checks)
    assert exit_code_for_result(result) == 0


def test_tournament_ops_fixture_fail(settings):
    fixture_bad = FixtureCheckResult(
        local_path=settings.ledger_path,
        upstream_url="https://example.com/fixtures.json",
        local_sha256="abc",
        upstream_sha256="def",
        local_match_count=100,
        upstream_match_count=104,
        changes=(),
        checked_at="2026-06-01T00:00:00Z",
    )
    with (
        patch("world_cup_bot.tournament_ops.check_fixtures", return_value=fixture_bad),
        patch("world_cup_bot.tournament_ops.discover_markets", return_value=[]),
        patch("world_cup_bot.tournament_ops.scan_mid_staleness", return_value=[]),
        patch("world_cup_bot.tournament_ops.cross_venue_scanner.run_scan") as mock_scan,
        patch(
            "world_cup_bot.tournament_ops._check_match_shock_readiness",
            return_value=MagicMock(status=CheckStatus.PASS),
        ),
    ):
        mock_scan.return_value = MagicMock(discoveries=[])
        result = run_tournament_ops_check(settings)
    assert not result.ok
    assert exit_code_for_result(result) == 1


def test_tournament_ops_discover_warn(settings):
    fixture_ok = FixtureCheckResult(
        local_path=settings.ledger_path,
        upstream_url="https://example.com/fixtures.json",
        local_sha256="abc",
        upstream_sha256="abc",
        local_match_count=104,
        upstream_match_count=104,
        changes=(),
        checked_at="2026-06-01T00:00:00Z",
    )
    discovery = MagicMock(in_config=False, to_dict=lambda: {"team": "Brazil"})
    with (
        patch("world_cup_bot.tournament_ops.check_fixtures", return_value=fixture_ok),
        patch("world_cup_bot.tournament_ops.discover_markets", return_value=[]),
        patch("world_cup_bot.tournament_ops.scan_mid_staleness", return_value=[]),
        patch("world_cup_bot.tournament_ops.cross_venue_scanner.run_scan") as mock_scan,
        patch(
            "world_cup_bot.tournament_ops._check_match_shock_readiness",
            return_value=MagicMock(status=CheckStatus.PASS),
        ),
    ):
        mock_scan.return_value = MagicMock(discoveries=[discovery])
        result = run_tournament_ops_check(settings, strict_discover=False)
    assert result.ok
    assert result.has_warnings
    assert exit_code_for_result(result) == 2


def test_match_shock_readiness_warns_without_tapes(settings, tmp_path):
    discovery = tmp_path / "data" / "local" / "match_markets.json"
    discovery.parent.mkdir(parents=True)
    discovery.write_text("[]", encoding="utf-8")
    with patch(
        "world_cup_bot.tournament_ops.resolve_project_path",
        side_effect=lambda p: discovery if "match_markets" in str(p) else tmp_path / str(p).split("/")[-1],
    ):
        # Use real resolve for config path
        from world_cup_bot.paths import resolve_project_path as real_resolve

        def _resolve(raw):
            s = str(raw)
            if s == "data/local/match_markets.json":
                return discovery
            if s == "config/shock_match.yaml":
                return real_resolve(s)
            if "tapes" in s or raw == settings.match_shock_tape_dir:
                return tmp_path / "tapes"
            return tmp_path / "shock.jsonl"

        with patch("world_cup_bot.tournament_ops.resolve_project_path", side_effect=_resolve):
            check = _check_match_shock_readiness(settings)
    assert check.status == CheckStatus.WARN
    assert "tapes" in check.detail.lower()


def test_match_shock_readiness_pass_with_tape(settings, tmp_path):
    discovery = tmp_path / "match_markets.json"
    discovery.write_text("[]", encoding="utf-8")
    tape_dir = tmp_path / "tapes"
    tape_dir.mkdir()
    (tape_dir / "sample.jsonl").write_text("{}\n", encoding="utf-8")

    from world_cup_bot.paths import resolve_project_path as real_resolve

    def _resolve(raw):
        s = str(raw)
        if s == "data/local/match_markets.json":
            return discovery
        if s == "config/shock_match.yaml":
            return real_resolve(s)
        if "tapes" in s:
            return tape_dir
        return tmp_path / "shock.jsonl"

    with patch("world_cup_bot.tournament_ops.resolve_project_path", side_effect=_resolve):
        check = _check_match_shock_readiness(settings)
    assert check.status == CheckStatus.PASS
