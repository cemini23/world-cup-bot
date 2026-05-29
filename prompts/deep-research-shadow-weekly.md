# Deep research — shadow mode weekly review

You are reviewing **shadow-mode** operation before live LP capital. Use ledger + readiness context — not directional predictions.

## Scope

Focus context includes:

- `ready` — preflight checks, shadow step progress, ledger quote_intent counts
- `pnl` — current logic_version ledger summary (may be null)

Reference: repo `SHADOW.md` phases 0–4.

## Research tasks

1. **Phase completion** — Which SHADOW phases are truly done vs checkbox theater?
2. **Plan discipline** — Enough `plan --record` sessions? Any conviction rows that never appeared in intents?
3. **Watch / reconcile** — Was `watch` run with L2 creds? Any reconcile-recovered fills in logs?
4. **Anomalies** — Quote intents for teams in cancel window; repeated failures; Gamma 403 history.
5. **Go-live gate** — Is operator ready for Phase 3 egress preflight? List blockers.

## Output format

Return **only**:

```json
{
  "review_week_ending": "2026-05-29",
  "shadow_phase_estimate": 1,
  "overall_verdict": "continue_shadow",
  "verdict_values": ["continue_shadow", "ready_for_egress_test", "ready_for_live_pilot", "halt"],
  "phase_status": [
    {"phase": 0, "name": "install", "status": "done", "evidence": "preflight gamma OK"},
    {"phase": 1, "name": "dry_plan", "status": "in_progress", "evidence": "2/3 days recorded"}
  ],
  "findings": [
    {"severity": "low", "finding": "...", "action": "run plan --record daily"}
  ],
  "metrics": {
    "quote_intents": 0,
    "distinct_plan_days": 0,
    "fills": 0,
    "preflight_ok": true
  },
  "blockers_before_live": ["non-US egress preflight not run", "..."],
  "operator_checklist_next_week": ["...", "..."]
}
```

No code changes — operator actions only.
