Research the FIFA World Cup 2026 **Group {{GROUP}}** advance-to-knockout landscape for a **Polymarket limit-order LP bot** (maker quotes only — not directional betting advice).

**Research goal:** For each of the four teams in Group {{GROUP}}, determine (1) realistic probability of advancing to the knockout stage, (2) whether Polymarket “advance” mids align with that research, and (3) which teams are suitable for **YES-heavy LP** (mid ≈ 20–80¢), **bilateral-only LP** (mid ≥ 90¢), **fade/watch only** (cross-venue divergence), or **skip**.

**Timeframe:** Research current as of {{DATE}}. Tournament: FIFA World Cup 2026 (USA / Canada / Mexico). Focus on previews, squads, and markets active in May–June 2026.

**Scope — include:**
- Group {{GROUP}} teams: {{FIXTURE_TEAMS}}
- Polymarket “advance to knockout” contract semantics for 2026
- Group preview sources: DeadBall TV, B Wade Picks, major sportsbooks, FIFA draw analysis
- Injury / suspension / manager news in the **last 14 days**
- Kalshi or sportsbook advance/qualifier prices where publicly visible (US-accessible)

**Scope — exclude:**
- Match-winner-only markets unless equivalent to knockout advance
- Live trading recommendations or position sizing for humans
- Pre-2026 historical World Cup nostalgia unless it affects 2026 squad strength

**Attached bot context (Gamma mids + current YAML tiers — verify against live Polymarket):**
```json
{{BOT_CONTEXT}}
```

**Tier definitions (match bot code):**
| Tier | Use when |
|------|----------|
| yes_conviction | Research-backed mid-tier advance; target mid 0.20–0.80 |
| bilateral_only | High mid / whale books; mandatory two-sided quoting above ~90¢ |
| fade_watch | PM vs Kalshi/books divergence ≥5pp — alert only, no auto YES |
| skip | Research says OUT or structurally untradeable for LP |

Default cap USD 2000; raise to 2500 only with strong multi-source conviction.

**Output format — produce a technical report with these sections:**
1. **Executive summary** (≤200 words) — who advances, LP posture for the group
2. **Group table** — columns: Team | Expected finish | P(advance) research | Polymarket mid | Gap (pp) | Recommended tier | LP note
3. **Team deep-dives** (one subsection per team) — squad news, path to advance, key risks
4. **Market mispricing** — teams where PM mid differs ≥10pp from research
5. **Calendar note** — first kickoff timing; any team inside a 10h pre-match cancel window
6. **Sources** — numbered list with URL and retrieval date
7. **Open questions** — what would change tiers if resolved
8. **Appendix: YAML patch JSON** — single JSON object:

```json
{
  "group": "{{GROUP}}",
  "confidence": "moderate|high|low",
  "teams": [
    {
      "team": "...",
      "recommended_tier": "yes_conviction|bilateral_only|fade_watch|skip|unchanged",
      "max_notional_usd": 2000,
      "advance_prob_research": 0.0,
      "mid_polymarket": 0.0,
      "gap_pp": 0,
      "rationale": "one sentence"
    }
  ],
  "stale_after": "YYYY-MM-DD"
}
```

**Citation requirements:** Minimum **12 sources**. Prefer primary sources (FIFA, official previews, Kalshi/Polymarket market pages, reputable preview channels). When sources conflict on group winner, show both estimates — do not average silently.

**Missing data:** If Polymarket or Kalshi price is unavailable, write **“unavailable — not verified live”**; do not invent mids.
