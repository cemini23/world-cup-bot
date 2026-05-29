Review **shadow-mode readiness** for a FIFA World Cup 2026 Polymarket LP bot before live capital. This is an **operational audit** — not a tournament prediction task.

**Research goal:** Given attached shadow/ledger context, assess SHADOW.md phases 0–4 completion, plan discipline, and blockers before non-US egress test or live pilot.

**Timeframe:** Review week ending {{DATE}}.

**Scope — include:**
- Attached `ready` preflight payload and `pnl` ledger summary
- Public Polymarket Gamma / CLOB geoblock documentation (US read vs trade)
- Best practices for shadow trading / dry-run LP bots
- Typical go-live checklist items: reconcile, watch/L2, preflight, conviction alignment

**Scope — exclude:**
- Which teams will win the World Cup
- Private keys, wallet addresses, server hostnames (not in context)

**Attached bot context (from operator machine):**
```json
{{BOT_CONTEXT}}
```

**Reference phases (SHADOW.md):**
- Phase 0: install / gamma reachability
- Phase 1: dry `plan --record` discipline
- Phase 2: watch + reconcile
- Phase 3: egress preflight (non-US)
- Phase 4: live pilot sizing

**Output format:**
1. **Overall verdict** — continue_shadow | ready_for_egress_test | ready_for_live_pilot | halt
2. **Phase status table** — Phase | Name | Status | Evidence from context
3. **Findings** — severity-ranked list with operator actions
4. **Metrics interpretation** — quote_intents, distinct plan days, fills (if any)
5. **Blockers before live** — numbered list
6. **Operator checklist — next 7 days**
7. **Appendix JSON:**

```json
{
  "review_week_ending": "{{DATE}}",
  "shadow_phase_estimate": 0,
  "overall_verdict": "continue_shadow",
  "blockers_before_live": [],
  "operator_checklist_next_week": []
}
```

**Citation requirements:** Cite SHADOW.md-style practices and Polymarket docs where relevant; **operational claims must reference attached JSON**, not invented metrics.

**Missing data:** If ledger is empty, say so explicitly — do not assume fills or plan days.
