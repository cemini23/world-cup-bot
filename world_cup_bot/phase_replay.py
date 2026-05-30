"""Phase router replay — JSONL timeline fixtures for PR3 regression tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from world_cup_bot import phase_router
from world_cup_bot.settlement_gate import PhaseSettlementStatus, SettlementGateReport


@dataclass(frozen=True)
class ReplayStep:
    ts: datetime
    label: str
    expect_phase: str
    expect_source: str | None = None
    expect_blocked_by: str | None = None
    settlement: dict[str, tuple[int, int]] | None = None
    completed_group_matches: int | None = None
    settlement_gate_enabled: bool = True
    match_gate_enabled: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ReplayStep:
        ts_raw = str(raw["ts"])
        if ts_raw.endswith("Z"):
            ts_raw = ts_raw[:-1] + "+00:00"
        ts = datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        settlement: dict[str, tuple[int, int]] | None = None
        if raw.get("settlement"):
            settlement = {}
            for pid, body in raw["settlement"].items():
                if isinstance(body, dict):
                    settlement[str(pid)] = (
                        int(body.get("total", 0)),
                        int(body.get("settled", 0)),
                    )
                elif isinstance(body, (list, tuple)) and len(body) >= 2:
                    settlement[str(pid)] = (int(body[0]), int(body[1]))

        return cls(
            ts=ts,
            label=str(raw.get("label") or raw["ts"]),
            expect_phase=str(raw["expect_phase"]),
            expect_source=raw.get("expect_source"),
            expect_blocked_by=raw.get("expect_blocked_by"),
            settlement=settlement,
            completed_group_matches=(
                int(raw["completed_group_matches"])
                if raw.get("completed_group_matches") is not None
                else None
            ),
            settlement_gate_enabled=bool(raw.get("settlement_gate_enabled", True)),
            match_gate_enabled=bool(raw.get("match_gate_enabled", False)),
        )


@dataclass(frozen=True)
class ReplayStepResult:
    step: ReplayStep
    tournament_phase: str
    source: str
    blocked_by: str | None
    passed: bool
    detail: str | None = None


@dataclass(frozen=True)
class ReplayReport:
    fixture: str
    total: int
    passed: int
    failed: int
    results: tuple[ReplayStepResult, ...]

    @property
    def ok(self) -> bool:
        return self.failed == 0


def load_replay_jsonl(path: Path) -> list[ReplayStep]:
    steps: list[ReplayStep] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            steps.append(ReplayStep.from_dict(json.loads(text)))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_no}: {exc}") from exc
    return steps


def settlement_report_from_step(step: ReplayStep) -> SettlementGateReport | None:
    if not step.settlement:
        return None
    by_phase = {
        pid: PhaseSettlementStatus(pid, total, settled)
        for pid, (total, settled) in step.settlement.items()
    }
    pending = tuple(
        pid for pid, st in by_phase.items() if st.total_markets > 0 and not st.all_settled
    )
    return SettlementGateReport(by_phase=by_phase, pending_phase_ids=pending)


def run_replay(
    config_path: Path,
    steps: list[ReplayStep],
    *,
    fixture_name: str = "replay",
    fixtures_path: Path | None = None,
) -> ReplayReport:
    results: list[ReplayStepResult] = []
    for step in steps:
        ctx = phase_router.resolve_phase_router(
            config_path,
            now=step.ts,
            enabled=True,
            settlement_gate_enabled=step.settlement_gate_enabled,
            settlement_report=settlement_report_from_step(step),
            match_gate_enabled=step.match_gate_enabled,
            fixtures_path=fixtures_path,
            completed_group_matches_override=step.completed_group_matches,
        )
        blocked = ctx.settlement_blocked_by or ctx.fifa_match_blocked_by
        passed = ctx.tournament_phase == step.expect_phase
        if step.expect_source is not None and ctx.source != step.expect_source:
            passed = False
        if step.expect_blocked_by is not None and blocked != step.expect_blocked_by:
            passed = False
        detail = None
        if not passed:
            detail = (
                f"got phase={ctx.tournament_phase} source={ctx.source} blocked={blocked}; "
                f"want phase={step.expect_phase} source={step.expect_source} "
                f"blocked={step.expect_blocked_by}"
            )
        results.append(
            ReplayStepResult(
                step=step,
                tournament_phase=ctx.tournament_phase,
                source=ctx.source,
                blocked_by=blocked,
                passed=passed,
                detail=detail,
            )
        )

    failed = sum(1 for r in results if not r.passed)
    return ReplayReport(
        fixture=fixture_name,
        total=len(results),
        passed=len(results) - failed,
        failed=failed,
        results=tuple(results),
    )
