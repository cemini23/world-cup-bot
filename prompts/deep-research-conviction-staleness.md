# Deep research — conviction YAML staleness refresh

You are auditing **research freshness** for all teams listed in `config/conviction.yaml`. The bot may be quoting on **stale** previews (injuries, friendlies, manager changes, market regime shifts).

## Scope

Focus context includes:

- `all_teams[]` — every non-unlisted YAML team with live Gamma + tier
- `yaml_summary` — list counts
- `cancel_window` — teams imminently playing

## Research tasks

1. **Staleness clock** — K82 synthesis date ~2026-05-29; flag teams not re-validated in 7+ days.
2. **News delta** — Search each **yes_conviction** and **fade_watch** team for material updates since last ingest.
3. **Mid regime change** — Compare context mid to prior research band; >15pp move without news → `human_review`.
4. **Tier drift** — Should any team move yes → bilateral, yes → fade, yes → skip, or reverse?
5. **Duplicate tier conflicts** — Mexico/England/Switzerland in both bilateral and fade; confirm fade still wins.

## Output format

Return **only**:

```json
{
  "audit_date": "2026-05-29",
  "staleness_threshold_days": 7,
  "summary": {
    "teams_reviewed": 28,
    "stale_count": 3,
    "tier_changes_recommended": 2,
    "urgent_skip": 1
  },
  "teams": [
    {
      "team": "Japan",
      "current_tier": "yes_heavy",
      "freshness": "stale",
      "last_research_date": "2026-05-20",
      "news_delta": "B Wade Japan 1st vs DeadBall Netherlands 1st split",
      "recommended_tier": "yes_conviction",
      "recommended_action": "reduce_cap",
      "max_notional_usd": 1500,
      "priority": "high",
      "sources": ["url"]
    }
  ],
  "yaml_patch_lines": [
    "# optional: literal YAML snippets operator can paste",
    "  Japan:",
    "    max_notional_usd: 1500"
  ],
  "no_change_teams": ["Turkey", "Colombia"],
  "next_audit_by": "2026-06-05"
}
```

Run weekly during group stage; pipe after `world-cup-bot scan --conviction`.
