from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    cmd = [sys.executable, "-m", "world_cup_bot", *args]
    return subprocess.run(cmd, capture_output=True, check=False, env=env)


def test_phase_status_overlap_prefers_latest_configured_state(tmp_path: Path):
    # Current date in this environment is 2026-05-31; make overlapping windows around it.
    cfg = tmp_path / "market_phases_overlap.yaml"
    cfg.write_text(
        """
version: 2
active_phase: group_advance
calendar: {}
phases:
  group_advance:
    description: "base"
    lp_eligible: true
tournament_states:
  alpha:
    calendar_start: "2026-05-01"
    calendar_end: "2026-06-30"
    scanner_phase_ids: [group_advance]
    lp_active_phases: [group_advance]
  zeta:
    calendar_start: "2026-05-15"
    calendar_end: "2026-06-15"
    scanner_phase_ids: [group_advance]
    lp_active_phases: [group_advance]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["WC_PHASE_ROUTER_ENABLED"] = "1"
    env["MARKET_PHASES_CONFIG"] = str(cfg)
    env["PHASE_ROUTER_OVERRIDE_PATH"] = str(tmp_path / "override.json")

    proc = _run_cli(["phase", "status", "--json"], env)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    payload = json.loads(proc.stdout.decode("utf-8"))
    # With overlap, router should choose latest by configured order ("zeta"), not alpha sort.
    assert payload["tournament_phase"] == "zeta"
    assert payload["source"] == "auto"


def test_phase_status_reports_forced_override_source(tmp_path: Path):
    cfg = Path(__file__).resolve().parents[1] / "config" / "market_phases.yaml"
    override = tmp_path / "phase_override.json"

    env = os.environ.copy()
    env["WC_PHASE_ROUTER_ENABLED"] = "1"
    env["MARKET_PHASES_CONFIG"] = str(cfg)
    env["PHASE_ROUTER_OVERRIDE_PATH"] = str(override)

    set_proc = _run_cli(["phase", "set", "quarterfinal"], env)
    assert set_proc.returncode == 0, set_proc.stderr.decode("utf-8", errors="replace")

    status_proc = _run_cli(["phase", "status", "--json"], env)
    assert status_proc.returncode == 0, status_proc.stderr.decode("utf-8", errors="replace")
    payload = json.loads(status_proc.stdout.decode("utf-8"))
    assert payload["tournament_phase"] == "quarterfinal"
    assert payload["source"] == "override_file"
