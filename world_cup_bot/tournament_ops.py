"""Bundled tournament health checks — fixture drift, conviction staleness, cross-venue discover."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from world_cup_bot import cross_venue_scanner
from world_cup_bot.config import Settings, match_shock_enabled, match_shock_live
from world_cup_bot.conviction_staleness import scan_mid_staleness
from world_cup_bot.cross_venue_config import load_cross_venue_config
from world_cup_bot.fixture_watch import (
    DEFAULT_UPSTREAM_URL,
    FixtureCheckResult,
    check_fixtures,
)
from world_cup_bot.match_shock_config import load_match_shock_config
from world_cup_bot.paths import resolve_project_path
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
            upstream_url=upstream_url or DEFAULT_UPSTREAM_URL,
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


def _check_match_shock_readiness(settings: Settings) -> TournamentCheck:
    """Module 8 pre-kickoff hygiene — discovery, tapes, promotion gates (K94/K97)."""
    cfg = load_match_shock_config()
    tape_dir = resolve_project_path(settings.match_shock_tape_dir)
    discovery = resolve_project_path("data/local/match_markets.json")
    ledger = resolve_project_path(settings.match_shock_ledger_path)
    shock_cfg_path = resolve_project_path("config/shock_match.yaml")

    warnings: list[str] = []
    if not shock_cfg_path.is_file():
        return TournamentCheck(
            id="match_shock_readiness",
            title="Match-shock readiness (Module 8)",
            status=CheckStatus.FAIL,
            detail="config/shock_match.yaml missing",
        )
    if not discovery.is_file():
        warnings.append(
            "run: world-cup-bot match-shock-discover --out data/local/match_markets.json"
        )
    tape_files = sorted(tape_dir.glob("**/*.jsonl")) if tape_dir.is_dir() else []
    if not tape_files:
        warnings.append(
            "no shock tapes — match-shock-export or WC_SHOCK_ENABLED=1 match-shock-record"
        )
    if cfg.enabled and not match_shock_enabled():
        warnings.append("shock_match.enabled=true but WC_SHOCK_ENABLED unset")
    if match_shock_live() and not cfg.enabled:
        warnings.append("WC_MATCH_SHOCK_LIVE=1 but shock_match.yaml enabled=false")
    if match_shock_live() and not ledger.is_file():
        warnings.append("live mode set but no shock ledger yet — paper soak first")

    detail_parts = [
        f"yaml enabled={cfg.enabled}",
        f"discovery={'yes' if discovery.is_file() else 'no'}",
        f"tapes={len(tape_files)}",
    ]
    if warnings:
        return TournamentCheck(
            id="match_shock_readiness",
            title="Match-shock readiness (Module 8)",
            status=CheckStatus.WARN,
            detail="; ".join(detail_parts + warnings),
            data={"warnings": warnings, "tape_count": len(tape_files)},
        )
    return TournamentCheck(
        id="match_shock_readiness",
        title="Match-shock readiness (Module 8)",
        status=CheckStatus.PASS,
        detail="; ".join(detail_parts),
        data={"tape_count": len(tape_files)},
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
        _check_match_shock_readiness(settings),
    )
    return TournamentOpsResult(checks=checks)


def exit_code_for_result(result: TournamentOpsResult) -> int:
    if not result.ok:
        return 1
    if result.has_warnings:
        return 2
    return 0
