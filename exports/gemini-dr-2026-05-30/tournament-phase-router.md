# Gemini DR — Tournament phase router spec (group → final)

Design **Module 1b / Phase Router** so one codebase switches strategy by tournament phase without manual rewrites after each round.

**Date:** 2026-05-30  
**Prerequisite reports:** 08-knockout-market-map, 09-inplay-pregame-lp-risks

## Research tasks

1. **Phase state machine** — States: `pre_tournament`, `group_stage`, `group_to_knockout_transition`, `round_of_32`, `round_of_16`, `quarterfinal`, `semifinal`, `third_place`, `final`, `post_tournament`. Transitions triggered by FIFA calendar + market resolution events.

2. **Per-phase strategy profile** — For each state define:
   - `scanner_phase_ids[]` (from 08 appendix)
   - `conviction_yaml` section or separate file?
   - `operating_overrides` (cancel hours, min_mid, bilateral threshold, daily adverse cap)
   - `cross_venue_enabled` Y/N

3. **Conviction carry-forward** — When Team X is eliminated in QF:
   - Auto-remove from all open phase markets
   - Cancel orders across phases (single `cancel --team`?)
   - Ledger attribution by `tournament_phase` field

4. **YAML schema proposal** — `config/tournament_phases.yaml` with example for group + R16 + reach-final

5. **CLI / systemd** — How operator sets `WC_TOURNAMENT_PHASE=group_stage` vs auto-detect from calendar + Gamma event mix

6. **Testing strategy** — Replay logs / fixture markets for phase transitions; shadow mode per phase

**Attached bot context:**
```json
{
  "dry_run": true,
  "conviction_config": "config/conviction.yaml",
  "cancel_window": [],
  "logic_version": "wc_advance_lp_v4",
  "market_phases_stub": "config/market_phases.yaml",
  "modules_to_extend": [
    "scanner",
    "conviction",
    "calendar_guard",
    "ledger"
  ]
}
```

## Output format

Return **only** this JSON (plus optional 1-page prose summary before it):

```json
{
  "module": "tournament_phase_router_v1",
  "state_machine": [{"state": "group_stage", "enter": "...", "exit": "..."}],
  "config_schema": {},
  "cli_proposal": ["world-cup-bot phase status", "world-cup-bot phase set round_of_16"],
  "ledger_fields_add": ["tournament_phase", "market_phase_id"],
  "migration_from_v1": ["extend scanner regex list", "..."],
  "estimated_effort_days": 0,
  "open_questions": []
}
```
