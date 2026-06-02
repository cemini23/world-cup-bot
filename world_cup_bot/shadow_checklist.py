"""Shadow-mode progress — checklist steps for UI + operators."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from world_cup_bot.config import Settings
from world_cup_bot.ledger import load_rows
from world_cup_bot.logic_version import load_strategy_version
from world_cup_bot.paths import resolve_project_path
from world_cup_bot.preflight import CheckStatus, run_preflight
from world_cup_bot.risk import shadow_net_pnl_ok


def _shadow_pnl_detail(settings: Settings, stats: dict[str, int]) -> str:
    if stats["fills"] == 0:
        return "No fills yet — gate applies after watch --record"
    spec = load_strategy_version(Path(settings.logic_version_config))
    _ok, detail = shadow_net_pnl_ok(Path(settings.ledger_path), spec)
    return detail


def _shadow_pnl_status(settings: Settings, stats: dict[str, int]) -> StepStatus:
    if stats["fills"] == 0:
        return StepStatus.DONE
    spec = load_strategy_version(Path(settings.logic_version_config))
    ok, _detail = shadow_net_pnl_ok(Path(settings.ledger_path), spec)
    return StepStatus.DONE if ok else StepStatus.WARN


class StepStatus(StrEnum):
    DONE = "done"
    PENDING = "pending"
    WARN = "warn"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ShadowStep:
    id: str
    phase: int
    title: str
    detail: str
    status: StepStatus
    cli: str | None = None


def _ledger_paths(settings: Settings) -> list[Path]:
    """Canonical ledger plus optional legacy paths (split-ledger recovery)."""
    paths: list[Path] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        p = Path(raw)
        if not p.is_file():
            return
        key = str(p.resolve())
        if key in seen:
            return
        seen.add(key)
        paths.append(p)

    add(str(Path(settings.ledger_path)))
    legacy = os.environ.get("WC_LEDGER_LEGACY_PATHS", "").strip()
    for part in legacy.split(","):
        part = part.strip()
        if part:
            add(str(resolve_project_path(part)))
    return paths


def _ledger_stats(settings: Settings) -> dict[str, int]:
    ledger_files = _ledger_paths(settings)
    if not ledger_files:
        return {
            "rows": 0,
            "quote_intents": 0,
            "fills": 0,
            "distinct_days": 0,
            "ledger_paths": 0,
        }

    spec = load_strategy_version(Path(settings.logic_version_config))
    quote_events = frozenset({"quote_intent", "quote_intent_dry_run"})
    quote_intents = 0
    fills = 0
    days: set[str] = set()
    rows = 0
    for path in ledger_files:
        scoped = [r for r in load_rows(path) if r.get("logic_version") == spec.version_id]
        rows += len(scoped)
        quote_intents += sum(1 for r in scoped if r.get("event") in quote_events)
        fills += sum(1 for r in scoped if r.get("event") == "order_fill")
        for r in scoped:
            ts = str(r.get("timestamp") or r.get("ts") or r.get("recorded_at") or "")
            if len(ts) >= 10:
                days.add(ts[:10])

    return {
        "rows": rows,
        "quote_intents": quote_intents,
        "fills": fills,
        "distinct_days": len(days),
        "ledger_paths": len(ledger_files),
    }


def build_shadow_steps(settings: Settings, *, test_auth: bool = False) -> list[ShadowStep]:
    """Evaluate shadow checklist from env + ledger (best-effort)."""
    stats = _ledger_stats(settings)
    preflight = run_preflight(settings, test_auth=test_auth)
    pf = {c.name: c for c in preflight.checks}

    gamma_ok = pf.get("gamma", None) and pf["gamma"].status == CheckStatus.PASS
    preflight_shadow_ok = preflight.ok or (
        settings.dry_run and all(c.status != CheckStatus.FAIL for c in preflight.checks)
    )

    l2_present = pf.get("l2_creds") and pf["l2_creds"].status == CheckStatus.PASS
    pk_present = bool(os.environ.get("POLYMARKET_PRIVATE_KEY", "").strip())

    geoblock = pf.get("geoblock")
    clob_auth_ok = pf.get("clob_auth") and pf["clob_auth"].status == CheckStatus.PASS
    geo_live_ok = geoblock and geoblock.status == CheckStatus.PASS
    geo_egress_ok = geo_live_ok or (
        geoblock is not None
        and geoblock.status == CheckStatus.WARN
        and clob_auth_ok
        and "egress-safe" in geoblock.detail
    )

    gamma_check = pf.get("gamma")
    gamma_detail = gamma_check.detail if gamma_check else "Run preflight"
    steps: list[ShadowStep] = [
        ShadowStep(
            id="install",
            phase=0,
            title="Install & preflight",
            detail=gamma_detail,
            status=StepStatus.DONE if gamma_ok and preflight_shadow_ok else StepStatus.WARN,
            cli="world-cup-bot preflight",
        ),
        ShadowStep(
            id="dry_plan",
            phase=1,
            title="Dry-run plan sessions",
            detail=(
                f"{stats['quote_intents']} quote intents across {stats['distinct_days']} day(s) "
                f"(target: ≥3 days with --record)"
                + (
                    f" — merged {stats['ledger_paths']} ledger file(s); "
                    "consolidate to one LEDGER_PATH / WC_LEDGER_PATH"
                    if stats.get("ledger_paths", 1) > 1
                    else ""
                )
            ),
            status=(
                StepStatus.DONE
                if stats["quote_intents"] > 0 and stats["distinct_days"] >= 3
                else StepStatus.PENDING
                if stats["quote_intents"] > 0
                else StepStatus.PENDING
            ),
            cli="world-cup-bot plan --record",
        ),
        ShadowStep(
            id="shadow_pnl",
            phase=1,
            title="Shadow net PnL floor",
            detail=_shadow_pnl_detail(settings, stats),
            status=_shadow_pnl_status(settings, stats),
            cli="world-cup-bot pnl --scope current",
        ),
        ShadowStep(
            id="watch",
            phase=2,
            title="Fill watch configured",
            detail="L2 creds set — run watch --record to validate WS + reconcile"
            if l2_present
            else "Set POLYMARKET_API_KEY/SECRET/PASSPHRASE for watch",
            status=StepStatus.DONE if l2_present and stats["fills"] > 0 else StepStatus.PENDING,
            cli="world-cup-bot watch --verbose --record",
        ),
        ShadowStep(
            id="egress",
            phase=3,
            title="Non-US egress preflight",
            detail=geoblock.detail if geoblock else "Run preflight from trading VPS",
            status=(
                StepStatus.DONE
                if geo_egress_ok
                else StepStatus.WARN
                if settings.dry_run and geoblock is not None and geoblock.status == CheckStatus.WARN
                else StepStatus.BLOCKED
                if geoblock is not None and geoblock.status == CheckStatus.FAIL
                else StepStatus.PENDING
            ),
            cli="world-cup-bot preflight",
        ),
        ShadowStep(
            id="live_ready",
            phase=4,
            title="Live pilot gate",
            detail=(
                "DRY_RUN=false + preflight PASS + py-clob-client-v2 on egress only"
                if not settings.dry_run
                else "Keep DRY_RUN=true until Phases 1–3 complete"
            ),
            status=(
                StepStatus.BLOCKED
                if settings.dry_run
                else StepStatus.DONE
                if preflight.ok and pk_present
                else StepStatus.WARN
            ),
            cli="DRY_RUN=false world-cup-bot preflight && world-cup-bot plan --record",
        ),
    ]
    return steps


def ready_payload(settings: Settings, *, test_auth: bool = False) -> dict:
    preflight = run_preflight(settings, test_auth=test_auth)
    steps = build_shadow_steps(settings, test_auth=test_auth)
    done = sum(1 for s in steps if s.status == StepStatus.DONE)
    return {
        "dry_run": settings.dry_run,
        "ledger_path": str(settings.ledger_path),
        "preflight_ok": preflight.ok,
        "preflight_checks": [
            {"name": c.name, "status": c.status.value, "detail": c.detail} for c in preflight.checks
        ],
        "shadow_steps": [
            {
                "id": s.id,
                "phase": s.phase,
                "title": s.title,
                "detail": s.detail,
                "status": s.status.value,
                "cli": s.cli,
            }
            for s in steps
        ],
        "shadow_progress": f"{done}/{len(steps)} steps",
        "ledger": _ledger_stats(settings),
        "docs": {"shadow": "SHADOW.md", "setup": "SETUP.md"},
    }
