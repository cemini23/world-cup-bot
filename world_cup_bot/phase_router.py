"""Module 1b — tournament phase router (FSM skeleton, DR 10)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot.fifa_match_gate import (
    FifaMatchGateConfig,
    apply_fifa_match_gate,
    check_fifa_match_gate,
)
from world_cup_bot.market_phases import (
    MarketPhasesConfig,
    TournamentStateSpec,
    get_market_phases_config,
)
from world_cup_bot.settlement_gate import SettlementGateReport


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
    source: str  # auto | env | override_file | settlement_gate | disabled
    cross_venue_enabled: bool
    scanner_phase_ids: tuple[str, ...]
    lp_active_phases: tuple[str, ...]
    operating_overrides: dict[str, float]
    forced: bool
    calendar_phase: str | None = None
    settlement_pending_phases: tuple[str, ...] = ()
    settlement_blocked_by: str | None = None
    fifa_match_blocked_by: str | None = None
    completed_group_matches: int | None = None

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
            "calendar_phase": self.calendar_phase,
            "settlement_pending_phases": list(self.settlement_pending_phases),
            "settlement_blocked_by": self.settlement_blocked_by,
            "fifa_match_blocked_by": self.fifa_match_blocked_by,
            "completed_group_matches": self.completed_group_matches,
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
    """Return (state_id, source) from calendar or overrides."""
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
        return sorted(matches)[-1], "auto"
    return "unknown", "auto"


def _phases_for_settlement_check(spec: TournamentStateSpec) -> tuple[str, ...]:
    return tuple(dict.fromkeys(spec.lp_active_phases + spec.scanner_phase_ids))


def apply_settlement_gate(
    config: MarketPhasesConfig,
    calendar_state_id: str,
    settlement: SettlementGateReport | None,
    *,
    gate_enabled: bool,
) -> tuple[str, str | None, tuple[str, ...]]:
    """Hold FSM in prior state until exiting phase markets settle."""
    if not gate_enabled or settlement is None or calendar_state_id == "unknown":
        return calendar_state_id, None, settlement.pending_phase_ids if settlement else ()

    ordered = config.ordered_tournament_state_ids()
    if calendar_state_id not in ordered:
        return calendar_state_id, None, settlement.pending_phase_ids

    candidate_idx = ordered.index(calendar_state_id)
    for i in range(candidate_idx, 0, -1):
        exiting_id = ordered[i - 1]
        exiting = config.tournament_states[exiting_id]
        if not exiting.require_full_settlement_to_exit:
            continue
        for pid in _phases_for_settlement_check(exiting):
            status = settlement.by_phase.get(pid)
            if status and status.total_markets > 0 and not status.all_settled:
                return exiting_id, pid, settlement.pending_phase_ids
    return calendar_state_id, None, settlement.pending_phase_ids


def effective_cancel_hours(ctx: PhaseRouterContext, default: float) -> float:
    raw = ctx.operating_overrides.get("cancel_hours")
    if raw is None:
        return default
    return float(raw)


def resolve_phase_router(
    config_path: Path,
    *,
    now: datetime | None = None,
    override_path: Path | None = None,
    enabled: bool = True,
    settlement_gate_enabled: bool = False,
    settlement_report: SettlementGateReport | None = None,
    match_gate_enabled: bool = False,
    fixtures_path: Path | None = None,
    completed_group_matches_override: int | None = None,
    fifa_gate_config: FifaMatchGateConfig | None = None,
) -> PhaseRouterContext:
    config = get_market_phases_config(config_path)
    gate_cfg = fifa_gate_config or config.fifa_match_gate
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
    calendar_state, cal_source = detect_tournament_state(
        config,
        now=now,
        env_override=None,
        file_override=None,
    )
    forced_state, forced_source = detect_tournament_state(
        config,
        now=now,
        env_override=env_phase,
        file_override=file_phase,
    )
    forced = forced_source in {"env", "override_file"}

    fifa_blocked: str | None = None
    completed_group: int | None = None

    if forced:
        state_id, source = forced_state, forced_source
        blocked_by = None
        pending: tuple[str, ...] = ()
    else:
        state_id, blocked_by, pending = apply_settlement_gate(
            config,
            calendar_state,
            settlement_report,
            gate_enabled=settlement_gate_enabled,
        )
        source = "settlement_gate" if blocked_by else cal_source

        if match_gate_enabled and blocked_by is None:
            gate_status = check_fifa_match_gate(
                calendar_state_id=calendar_state,
                gate_config=gate_cfg,
                now=now or datetime.now(UTC),
                fixtures_path=fixtures_path,
                completed_override=completed_group_matches_override,
            )
            completed_group = gate_status.completed_group_matches
            hold_state, fifa_blocked = apply_fifa_match_gate(
                calendar_state,
                gate_status,
                gate_enabled=True,
            )
            if fifa_blocked:
                state_id = hold_state
                blocked_by = None
                source = "fifa_match_gate"

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
            calendar_phase=calendar_state,
            settlement_pending_phases=pending,
            settlement_blocked_by=blocked_by,
            fifa_match_blocked_by=fifa_blocked,
            completed_group_matches=completed_group,
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

    if lp_active:
        active_market_phase = lp_active[0]
    elif scanner_ids:
        active_market_phase = scanner_ids[0]
    else:
        active_market_phase = market_phase_id

    return PhaseRouterContext(
        tournament_phase=state_id,
        market_phase_id=active_market_phase,
        source=source,
        cross_venue_enabled=spec.cross_venue_enabled,
        scanner_phase_ids=scanner_ids,
        lp_active_phases=lp_active,
        operating_overrides=overrides,
        forced=forced,
        calendar_phase=calendar_state,
        settlement_pending_phases=pending,
        settlement_blocked_by=blocked_by,
        fifa_match_blocked_by=fifa_blocked,
        completed_group_matches=completed_group,
    )


def lp_quoting_allowed(ctx: PhaseRouterContext, *, market_phase_id: str | None = None) -> bool:
    """True when router allows LP on the given market phase."""
    if ctx.tournament_phase == "disabled":
        return True
    phase = market_phase_id or ctx.market_phase_id
    return phase in ctx.lp_active_phases


def cross_venue_allowed(ctx: PhaseRouterContext) -> bool:
    if ctx.tournament_phase == "disabled":
        return True
    return ctx.cross_venue_enabled
