"""Module 1b — tournament phase router (FSM skeleton, DR 10)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot.market_phases import (
    MarketPhasesConfig,
    TournamentStateSpec,
    load_market_phases_config,
)


def _parse_iso(ts: str) -> datetime:
    text = ts.strip()
    if len(text) == 10:
        return datetime.fromisoformat(text).replace(tzinfo=UTC)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _state_contains(now: datetime, spec: TournamentStateSpec) -> bool:
    start = _parse_iso(spec.calendar_start)
    end = _parse_iso(spec.calendar_end)
    return start <= now < end


@dataclass(frozen=True)
class PhaseRouterContext:
    tournament_phase: str
    market_phase_id: str
    source: str  # auto | env | override_file
    cross_venue_enabled: bool
    scanner_phase_ids: tuple[str, ...]
    lp_active_phases: tuple[str, ...]
    operating_overrides: dict[str, float]
    forced: bool

    def to_status_dict(self) -> dict[str, Any]:
        return {
            "tournament_phase": self.tournament_phase,
            "market_phase_id": self.market_phase_id,
            "source": self.source,
            "cross_venue_enabled": self.cross_venue_enabled,
            "scanner_phase_ids": list(self.scanner_phase_ids),
            "lp_active_phases": list(self.lp_active_phases),
            "operating_overrides": self.operating_overrides,
            "forced": self.forced,
        }


def default_override_path(project_root: Path | None = None) -> Path:
    from world_cup_bot.paths import resolve_project_path

    rel = os.environ.get("PHASE_ROUTER_OVERRIDE_PATH", "data/local/phase_router_override.json")
    return resolve_project_path(rel)


def read_forced_state(override_path: Path) -> str | None:
    if not override_path.is_file():
        return None
    try:
        data = json.loads(override_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    state = data.get("tournament_phase") or data.get("forced_state")
    return str(state).strip() if state else None


def write_forced_state(override_path: Path, tournament_phase: str) -> None:
    override_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tournament_phase": tournament_phase,
        "set_at": datetime.now(UTC).isoformat(),
    }
    override_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def clear_forced_state(override_path: Path) -> None:
    if override_path.is_file():
        override_path.unlink()


def detect_tournament_state(
    config: MarketPhasesConfig,
    *,
    now: datetime | None = None,
    env_override: str | None = None,
    file_override: str | None = None,
) -> tuple[str, str]:
    """Return (state_id, source)."""
    if env_override:
        return env_override.strip(), "env"
    if file_override:
        return file_override.strip(), "override_file"

    now = now or datetime.now(UTC)
    matches = [
        spec.state_id for spec in config.tournament_states.values() if _state_contains(now, spec)
    ]
    if len(matches) == 1:
        return matches[0], "auto"
    if len(matches) > 1:
        # Prefer lexicographically last defined state when windows overlap (transition days)
        return sorted(matches)[-1], "auto"
    return "unknown", "auto"


def resolve_phase_router(
    config_path: Path,
    *,
    now: datetime | None = None,
    override_path: Path | None = None,
    enabled: bool = True,
) -> PhaseRouterContext:
    config = load_market_phases_config(config_path)
    market_phase_id = config.active_phase

    if not enabled or not config.tournament_states:
        return PhaseRouterContext(
            tournament_phase="disabled",
            market_phase_id=market_phase_id,
            source="disabled",
            cross_venue_enabled=True,
            scanner_phase_ids=(market_phase_id,),
            lp_active_phases=(market_phase_id,),
            operating_overrides={},
            forced=False,
        )

    ovr_path = override_path or default_override_path()
    env_phase = os.environ.get("WC_TOURNAMENT_PHASE", "").strip() or None
    file_phase = read_forced_state(ovr_path)
    state_id, source = detect_tournament_state(
        config,
        now=now,
        env_override=env_phase,
        file_override=file_phase,
    )
    forced = source in {"env", "override_file"}

    spec = config.tournament_states.get(state_id)
    if spec is None:
        return PhaseRouterContext(
            tournament_phase=state_id,
            market_phase_id=market_phase_id,
            source=source,
            cross_venue_enabled=True,
            scanner_phase_ids=(market_phase_id,),
            lp_active_phases=(market_phase_id,),
            operating_overrides={},
            forced=forced,
        )

    scanner_ids = tuple(spec.scanner_phase_ids or [market_phase_id])
    lp_active = tuple(spec.lp_active_phases or [market_phase_id])
    overrides = {
        k: v
        for k, v in {
            "cancel_hours": spec.operating_overrides.cancel_hours,
            "min_mid": spec.operating_overrides.min_mid,
            "bilateral_threshold": spec.operating_overrides.bilateral_threshold,
            "daily_adverse_cap": spec.operating_overrides.daily_adverse_cap,
        }.items()
        if v is not None
    }

    return PhaseRouterContext(
        tournament_phase=state_id,
        market_phase_id=market_phase_id,
        source=source,
        cross_venue_enabled=spec.cross_venue_enabled,
        scanner_phase_ids=scanner_ids,
        lp_active_phases=lp_active,
        operating_overrides=overrides,
        forced=forced,
    )


def lp_quoting_allowed(ctx: PhaseRouterContext, *, market_phase_id: str | None = None) -> bool:
    """True when router allows LP on the given market phase (v1: group_advance only)."""
    if ctx.tournament_phase == "disabled":
        return True
    phase = market_phase_id or ctx.market_phase_id
    return phase in ctx.lp_active_phases
