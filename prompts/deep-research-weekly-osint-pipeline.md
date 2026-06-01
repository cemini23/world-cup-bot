# Deep research — weekly conviction review pipeline

Use for a **weekly** research pass (external news, cross-venue maps, shadow diagnostics) — not for daily `conviction.yaml` edits.

## Scope

Combine:

1. **Bot context** from `world-cup-bot research run weekly-osint-pipeline --json`
2. **External sources** — 5–10 URLs or videos (injury news, Polymarket/Kalshi depth, FIFA fixtures)
3. **Optional synthesis tool** (NotebookLM, Claude, Gemini) for long-form reading offload
4. **Output** — one markdown brief in your notes repo or vault; human applies `conviction.yaml` changes

## Research tasks

1. **Conviction drift** — Any team in `per_team` still stale vs this week's injury/roster news?
2. **Cross-venue** — New Polymarket advance slugs or Kalshi ticker map gaps?
3. **Shadow** — `negative_filter_summary` trends; are skips selection vs liquidity?
4. **Phase router** — Upcoming `market_phases.yaml` windows needing flag review?
5. **Scope discipline** — Recommend config/skill changes only; do not invent new bot modules.

## Output format

Return **only**:

```json
{
  "week_ending": "2026-06-01",
  "conviction_patches": [
    {"team": "Canada", "recommended_mode": "fade_watch", "evidence": "...", "confidence": "medium"}
  ],
  "cross_venue_actions": ["refresh discover timer", "..."],
  "shadow_notes": ["..."],
  "no_go": ["do not enable live-plan timer", "..."]
}
```

Human gate: discuss takeaways before editing `config/conviction.yaml` or enabling live timers.
