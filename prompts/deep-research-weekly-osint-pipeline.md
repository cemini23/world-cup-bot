# Deep research — weekly OSINT pipeline (Monokern lane)

Use when the OSINT wiki **weekly** cadence runs (NotebookLM + vault markdown), not for daily `conviction.yaml` edits.

## Scope

Combine:

1. **Bot context** from `world-cup-bot research run weekly-osint-pipeline --json`
2. **External sources** — 5–10 URLs or videos (injury news, PM/Kalshi depth, FIFA fixtures)
3. **NotebookLM** (laptop `notebooklm-py`) for synthesis — offload heavy reading from Claude tokens
4. **Output** — one markdown brief under OSINT `wiki/sweeps/` or operator vault; human applies `conviction.yaml` changes

Reference: OSINT `@concepts/monokern-compounding-research-pipeline.md`, `@concepts/harness-updating-vs-benefit-nonmonotonic.md`.

## Research tasks

1. **Conviction drift** — Any team in `per_team` still stale vs this week's injury/roster news?
2. **Cross-venue** — New PM advance slugs or Kalshi ticker map gaps?
3. **Shadow** — `negative_filter_summary` trends; are skips selection vs liquidity?
4. **Phase router** — Upcoming `market_phases.yaml` windows needing flag review?
5. **Harness discipline** — Recommend config/skill changes only; do not invent new bot modules.

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
  "wiki_pages_to_update": ["@sources/...", "@concepts/..."],
  "no_go": ["do not enable live-plan timer", "..."]
}
```

Human gate: discuss takeaways before editing `config/conviction.yaml` or enabling prod flags.
