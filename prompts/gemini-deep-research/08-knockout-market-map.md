# Gemini DR — WC 2026 knockout-round market map (Polymarket + Kalshi)

Map **every tournament phase** after the group stage so World Cup Bot can extend beyond `advance to knockout` without rewriting from scratch each round.

**Date:** {{DATE}}  
**Bot today:** Module 1 scanner regex = `Will {TEAM} advance to the knockout stages…` only (group-stage conviction LP).

## Research tasks

1. **Polymarket event inventory** — List active + expected slugs/events for:
   - Group: advance to knockout (current)
   - Knockout: Round of 32 / Round of 16 (48-team format naming on PM)
   - Quarterfinal, Semifinal, Final reach (`Nation to Reach Final` style)
   - **Match-level** markets (win/draw, advance in tie, ET pens) — LP eligibility?
   - Winner / top scorer / special (out of scope for LP but note resolution coupling)

2. **Resolution rules diff** — Table per market type:
   - Trigger for immediate `No` on elimination
   - Postponement / cancellation deadlines (compare advance vs final vs match)
   - Source of truth (FIFA vs consensus reporting)

3. **Kalshi parity** — Which knockout legs exist on Kalshi for WC 2026? Ticker patterns for cross-venue Module 6.

4. **Scanner regex proposal** — YAML-ready patterns for `config/market_phases.yaml`:
   - `phase_id`, `gamma_search_query`, `title_regex`, `resolution_class`, `lp_eligible` (Y/N)

5. **Phase transition calendar** — FIFA 2026 dates: last group match → R32 draw → each knockout window. When do advance markets **resolve** vs when do R16/QF markets **open**?

6. **Reward params** — Do knockout / match markets carry LP rewards? Typical `rewardsMinSize`, `rewardsMaxSpread` vs group advance.

**Attached bot context:**
```json
{{BOT_CONTEXT}}
```

## Output format

1. Executive summary — v2 bot should support phases [list] in priority order
2. Market inventory table — Phase | PM event/slug pattern | Example team | Resolves when | LP rewards?
3. Resolution risk matrix — top 5 oracle/timing mismatches across phases
4. Kalshi map draft — 10 example pairs for cross-venue
5. **Appendix JSON:**

```json
{
  "market_phases": [
    {
      "phase_id": "group_advance",
      "title_regex": "^Will (.+?) advance to the knockout stages",
      "lp_eligible": true,
      "scanner_priority": 1,
      "notes": "..."
    },
    {
      "phase_id": "reach_final",
      "title_regex": "...",
      "lp_eligible": true,
      "scanner_priority": 2
    }
  ],
  "config_file_proposal": "config/market_phases.yaml",
  "implementation_effort_days": 0
}
```

Do **not** include private keys or prod hostnames.
