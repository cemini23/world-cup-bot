Audit **research freshness** for all teams in a World Cup 2026 Polymarket LP bot’s conviction config (`config/conviction.yaml`). Last full synthesis ~ **2026-05-29** (DeadBall + B Wade + prior Gemini reports).

**Research goal:** Find teams where YAML tiers or caps are **stale** due to injuries, friendlies, manager changes, or >15pp Polymarket mid moves without explained news. Recommend tier moves: yes_conviction ↔ bilateral_only ↔ fade_watch ↔ skip.

**Timeframe:** Audit as of {{DATE}}. Flag anything not re-validated in **7+ days**.

**Scope — include:**
- Every team in attached `all_teams` list with current Gamma mid and YAML tier
- News delta for all **yes_conviction** and **fade_watch** teams since 2026-05-22
- Duplicate tier conflicts (e.g. Mexico/England in both bilateral and fade — confirm fade precedence)
- Teams in cancel window (imminent kickoff) — urgent skip review

**Scope — exclude:**
- Rewriting bot code or operating thresholds
- Teams with `mode: skip` unless news suggests re-opening

**Attached bot context:**
```json
{{BOT_CONTEXT}}
```

**Output format:**
1. **Audit summary** — teams reviewed, stale count, urgent actions
2. **Stale team table** — Team | Current tier | Freshness | News delta | Recommended tier | Priority
3. **No-change list** — teams confirmed still valid
4. **YAML patch snippets** — literal YAML lines operator can paste into `per_team:` or tier lists
5. **Next audit date**
6. **Sources**
7. **Appendix JSON:**

```json
{
  "audit_date": "{{DATE}}",
  "summary": {"teams_reviewed": 0, "stale_count": 0, "tier_changes_recommended": 0},
  "teams": [{"team": "...", "current_tier": "...", "freshness": "fresh|stale", "recommended_tier": "...", "recommended_action": "unchanged|reduce_cap|skip|upgrade", "priority": "low|medium|high"}],
  "next_audit_by": "YYYY-MM-DD"
}
```

**Citation requirements:** Minimum **20 source hits** across the team set (not 20 per team); every recommended tier change must cite ≥1 source dated within 14 days or explain “mid regime change only”.

**Missing data:** Teams with no recent news → mark `freshness: assumed_fresh` and say what would falsify.
