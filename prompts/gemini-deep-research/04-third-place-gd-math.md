Research **third-place advancement math** for the **2026 FIFA World Cup** (48 teams, 12 groups × 4, **8 best third-place teams** advance). Output updates conviction tiers for teams whose knockout path depends on finishing 3rd on points / goal difference.

**Research goal:** For each third-place candidate team, estimate P(advance via 3rd) vs P(advance overall), compare to Polymarket mids, and recommend LP posture (normal / reduced cap / skip).

**Timeframe:** Current as of {{DATE}}. Use 2026 format rules and current group previews.

**Scope — include:**
- Third-place candidate teams (attached list)
- FIFA tiebreak order: points → GD → goals scored → H2H → fair play → lots
- B Wade / DeadBall third-place explainers for 2026
- Group finish projections (1st / 2nd / 3rd / OUT) per candidate
- GD sensitivity: likely rank among 12 third-place teams if they finish 3rd on 3–4 points

**Scope — exclude:**
- 32-team World Cup format
- Teams already locked as group winners in research consensus

**Attached bot context:**
```json
{{BOT_CONTEXT}}
```

**Output format:**
1. **Format primer** — 48-team third-place rules in plain English (≤150 words)
2. **Candidate ranking table** — Team | Expected finish | P(3rd) | P(advance\|3rd) | P(advance total) | PM mid | Mispricing (pp) | LP risk
3. **Borderline thirds ranked** — top 8 likely to survive vs cut line
4. **Upgrade/downgrade list** — YAML tier changes recommended
5. **Sources**
6. **Appendix JSON:**

```json
{
  "format_notes": "48-team, 12 groups, 8 best third-place advance",
  "candidates": [{"team": "...", "expected_group_finish": "3rd", "p_advance_overall": 0.0, "gamma_mid": 0.0, "yaml_recommendation": "yes_conviction|reduce|skip", "lp_risk": "normal|elevated|high"}],
  "teams_to_downgrade": [],
  "teams_to_upgrade": [],
  "confidence": "tentative|moderate|high"
}
```

**Citation requirements:** Minimum **10 sources**; include at least one explainer on 2026 third-place mechanics.

**Missing data:** If GD rank among thirds is uncertain, show scenario range (optimistic / base / pessimistic) — do not single-point estimate without labeling assumptions.
