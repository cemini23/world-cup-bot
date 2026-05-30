"""Load config/market_phases.yaml — scanner phases + tournament FSM states (DR 10)."""

from __future__ import annotations

import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from world_cup_bot.fifa_match_gate import FifaMatchGateConfig

_config_cache: dict[str, MarketPhasesConfig] = {}


@dataclass(frozen=True)
class OperatingOverrides:
    cancel_hours: float | None = None
    min_mid: float | None = None
    bilateral_threshold: float | None = None
    daily_adverse_cap: float | None = None


@dataclass(frozen=True)
class MarketPhaseSpec:
    phase_id: str
    description: str = ""
    title_regex: str | None = None
    gamma_search: str | None = None
    resolution_class: str | None = None
    lp_eligible: bool = False
    scanner_priority: int = 99
    conviction_config: str | None = None
    status: str = "research"


@dataclass(frozen=True)
class TournamentStateSpec:
    state_id: str
    calendar_start: str
    calendar_end: str
    scanner_phase_ids: list[str] = field(default_factory=list)
    lp_active_phases: list[str] = field(default_factory=list)
    operating_overrides: OperatingOverrides = field(default_factory=OperatingOverrides)
    cross_venue_enabled: bool = True
    require_full_settlement_to_exit: bool = False


@dataclass(frozen=True)
class MarketPhasesConfig:
    version: int
    active_phase: str
    calendar: dict[str, str]
    phases: dict[str, MarketPhaseSpec]
    tournament_states: dict[str, TournamentStateSpec]
    cancel_hours_by_phase: dict[str, float]
    fifa_match_gate: FifaMatchGateConfig = field(default_factory=FifaMatchGateConfig)

    def phase_spec(self, phase_id: str) -> MarketPhaseSpec | None:
        return self.phases.get(phase_id)

    def ordered_tournament_state_ids(self) -> list[str]:
        return sorted(
            self.tournament_states.keys(),
            key=lambda sid: self.tournament_states[sid].calendar_start,
        )


def _parse_operating(raw: dict[str, Any] | None) -> OperatingOverrides:
    if not raw:
        return OperatingOverrides()
    return OperatingOverrides(
        cancel_hours=raw.get("cancel_hours"),
        min_mid=raw.get("min_mid"),
        bilateral_threshold=raw.get("bilateral_threshold"),
        daily_adverse_cap=raw.get("daily_adverse_cap"),
    )


def _parse_tournament_state(state_id: str, raw: dict[str, Any]) -> TournamentStateSpec:
    return TournamentStateSpec(
        state_id=state_id,
        calendar_start=str(raw["calendar_start"]),
        calendar_end=str(raw["calendar_end"]),
        scanner_phase_ids=list(raw.get("scanner_phase_ids") or []),
        lp_active_phases=list(raw.get("lp_active_phases") or []),
        operating_overrides=_parse_operating(raw.get("operating_overrides")),
        cross_venue_enabled=bool(raw.get("cross_venue_enabled", True)),
        require_full_settlement_to_exit=bool(raw.get("require_full_settlement_to_exit", False)),
    )


def load_market_phases_config(path: Path) -> MarketPhasesConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    phases: dict[str, MarketPhaseSpec] = {}
    for pid, body in (raw.get("phases") or {}).items():
        if not isinstance(body, dict):
            continue
        phases[pid] = MarketPhaseSpec(
            phase_id=pid,
            description=str(body.get("description") or ""),
            title_regex=body.get("title_regex"),
            gamma_search=body.get("gamma_search"),
            resolution_class=body.get("resolution_class"),
            lp_eligible=bool(body.get("lp_eligible", False)),
            scanner_priority=int(body.get("scanner_priority") or 99),
            conviction_config=body.get("conviction_config"),
            status=str(body.get("status") or "research"),
        )

    tournament_states: dict[str, TournamentStateSpec] = {}
    for sid, body in (raw.get("tournament_states") or {}).items():
        if isinstance(body, dict) and "calendar_start" in body and "calendar_end" in body:
            tournament_states[sid] = _parse_tournament_state(sid, body)

    return MarketPhasesConfig(
        version=int(raw.get("version") or 1),
        active_phase=str(raw.get("active_phase") or "group_advance"),
        calendar=dict(raw.get("calendar") or {}),
        phases=phases,
        tournament_states=tournament_states,
        cancel_hours_by_phase={
            str(k): float(v) for k, v in (raw.get("cancel_hours_by_phase") or {}).items()
        },
        fifa_match_gate=FifaMatchGateConfig.from_market_phases_raw(raw.get("fifa_match_gate")),
    )


def get_market_phases_config(path: Path) -> MarketPhasesConfig:
    key = str(path.resolve())
    cached = _config_cache.get(key)
    if cached is not None:
        return cached
    loaded = load_market_phases_config(path)
    _config_cache[key] = loaded
    return loaded


def invalidate_market_phases_cache(path: Path | None = None) -> None:
    if path is None:
        _config_cache.clear()
        return
    _config_cache.pop(str(path.resolve()), None)


def install_sigusr1_reload(path: Path) -> None:
    """Re-parse market_phases.yaml on SIGUSR1 (long-running daemons)."""

    def _handler(signum: int, frame: object) -> None:
        invalidate_market_phases_cache(path)
        try:
            from world_cup_bot import event_log

            event_log.log_event(
                "config_reload",
                signal="SIGUSR1",
                target="market_phases",
                path=str(path),
            )
        except Exception:
            pass

    signal.signal(signal.SIGUSR1, _handler)
