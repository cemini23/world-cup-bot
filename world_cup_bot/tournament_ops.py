"""Bundled tournament health checks — fixture drift, conviction staleness, cross-venue discover."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from world_cup_bot import cross_venue_scanner
from world_cup_bot.config import Settings
from world_cup_bot.conviction_staleness import scan_mid_staleness
from world_cup_bot.cross_venue_config import load_cross_venue_config
from world_cup_bot.fixture_watch import FixtureCheckResult, check_fixtures
from world_cup_bot.scanner import discover_markets


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class TournamentCheck:
    id: str
    title: str
    status: CheckStatus
    detail: str
    data: dict[str, Any] | None = None


@dataclass(frozen=True)
class TournamentOpsResult:
    checks: tuple[TournamentCheck, ...]

    @property
    def ok(self) -> bool:
        return all(c.status != CheckStatus.FAIL for c in self.checks)

    @property
    def has_warnings(self) -> bool:
        return any(c.status == CheckStatus.WARN for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "has_warnings": self.has_warnings,
            "checks": [
                {
                    "id": c.id,
                    "title": c.title,
                    "status": c.status,
                    "detail": c.detail,
                    "data": c.data,
                }
                for c in self.checks
            ],
        }


def _check_fixtures(
    *,
    local_path: Path | None = None,
    upstream_url: str | None = None,
) -> TournamentCheck:
    try:
        result: FixtureCheckResult = check_fixtures(
            local_path=local_path,
            upstream_url=upstream_url,
        )
    except Exception as exc:  # noqa: BLE001
        return TournamentCheck(
            id="fixtures",
            title="Fixture drift (openfootball)",
            status=CheckStatus.FAIL,
            detail=str(exc),
        )
    if result.has_changes:
        return TournamentCheck(
            id="fixtures",
            title="Fixture drift (openfootball)",
            status=CheckStatus.FAIL,
            detail=(
                f"Drift: local {result.local_match_count} vs upstream "
                f"{result.upstream_match_count} matches ({len(result.changes)} change(s))"
            ),
            data=result.to_dict(),
        )
    return TournamentCheck(
        id="fixtures",
        title="Fixture drift (openfootball)",
        status=CheckStatus.PASS,
        detail=f"In sync ({result.local_match_count} matches)",
        data=result.to_dict(),
    )


def _check_conviction_staleness(
    settings: Settings,
    *,
    threshold_pp: float = 15.0,
) -> TournamentCheck:
    markets = discover_markets(
        settings.gamma_url,
        min_hours_before_kickoff=settings.min_hours_before_kickoff,
    )
    alerts = scan_mid_staleness(
        markets,
        ledger_path=Path(settings.ledger_path),
        threshold_pp=threshold_pp,
    )
    if alerts:
        return TournamentCheck(
            id="conviction_staleness",
            title="Conviction mid staleness",
            status=CheckStatus.FAIL,
            detail=f"{len(alerts)} team(s) moved ≥{threshold_pp:.0f}pp vs ledger baseline",
            data={"alerts": [a.to_dict() for a in alerts]},
        )
    return TournamentCheck(
        id="conviction_staleness",
        title="Conviction mid staleness",
        status=CheckStatus.PASS,
        detail=f"No mid moves ≥{threshold_pp:.0f}pp vs ledger quote_intent baseline",
    )


def _check_cross_venue_discover(
    settings: Settings,
    *,
    strict: bool = False,
) -> TournamentCheck:
    cfg = load_cross_venue_config(Path(settings.cross_venue_config))
    result = cross_venue_scanner.run_scan(
        cfg,
        gamma_url=settings.gamma_url,
        kalshi_base_url=settings.kalshi_base_url,
        include_discoveries=True,
    )
    new = [d for d in result.discoveries if not d.in_config]
    if not new:
        return TournamentCheck(
            id="cross_venue_discover",
            title="Cross-venue pair discovery",
            status=CheckStatus.PASS,
            detail=f"All {len(result.discoveries)} matched pair(s) in config",
            data={"new_pairs": 0, "total_matched": len(result.discoveries)},
        )
    status = CheckStatus.FAIL if strict else CheckStatus.WARN
    return TournamentCheck(
        id="cross_venue_discover",
        title="Cross-venue pair discovery",
        status=status,
        detail=f"{len(new)} new pair(s) not in config ({len(result.discoveries)} total matched)",
        data={
            "new_pairs": len(new),
            "total_matched": len(result.discoveries),
            "discoveries": [d.to_dict() for d in new[:20]],
        },
    )


def run_tournament_ops_check(
    settings: Settings,
    *,
    threshold_pp: float = 15.0,
    strict_discover: bool = False,
    fixture_local: Path | None = None,
    fixture_upstream_url: str | None = None,
) -> TournamentOpsResult:
    checks = (
        _check_fixtures(local_path=fixture_local, upstream_url=fixture_upstream_url),
        _check_conviction_staleness(settings, threshold_pp=threshold_pp),
        _check_cross_venue_discover(settings, strict=strict_discover),
    )
    return TournamentOpsResult(checks=checks)


def exit_code_for_result(result: TournamentOpsResult) -> int:
    if not result.ok:
        return 1
    if result.has_warnings:
        return 2
    return 0
