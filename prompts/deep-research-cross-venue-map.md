# Deep research — Polymarket ↔ Kalshi cross-venue map

You are building the **Module 6 alert-only cross-venue scanner** (not auto-execution). Map **semantically equivalent** advance/qualifier contracts and flag **≥5pp** probability gaps after fees.

## Scope

Focus context includes:

- `fade_watch_teams` — YAML list (USA, England, Croatia, Switzerland, Mexico, …)
- `markets[]` — live Polymarket mids
- `known_research_flags` — prior Gemini/book vs Kalshi divergences **[verify live]**

## Research tasks

1. **Kalshi catalog** — For each team, find the Kalshi event/market for *advance* or *group qualification* (not match winner unless equivalent).
2. **Rules hash** — Compare resolution criteria: knockout advance vs group winner vs R16; note **oracle mismatch** risk.
3. **Live prices** — PM mid vs Kalshi implied prob (yes ask or mid); compute gap in percentage points.
4. **Fee model** — Kalshi ~7% on profit; PM maker rebates vary — use **≥5pp raw** as alert threshold, note if net edge survives fees.
5. **Ticker map** — Stable identifiers for a future `config/cross_venue.yaml`.

Search: Kalshi API docs, `site:kalshi.com World Cup 2026 {Team}`, Polymarket Gamma slug for same team.

## Hard rules

- **Alert-only** — never recommend auto-hedge legs in v1.
- If contracts are **not equivalent**, set `equivalent: false` and do not compute arb.
- USA/Mexico home-nation flow — treat size limits as operator policy, not arb.

## Output format

Return **only** a JSON array:

```json
[
  {
    "team": "Switzerland",
    "polymarket": {
      "condition_id": "0x...",
      "question": "Will Switzerland advance...",
      "mid": 0.88,
      "source": "gamma_context"
    },
    "kalshi": {
      "event_ticker": "KXMVC...",
      "market_ticker": "...",
      "title": "...",
      "implied_prob": 0.55,
      "source_url": "https://..."
    },
    "equivalent": true,
    "rules_match_notes": "both advance to knockout",
    "gap_pp": 33,
    "alert": true,
    "fee_adjusted_edge_pp": 26,
    "recommended_action": "fade_watch_alert",
    "confidence": "tentative",
    "verified_at": "2026-05-29"
  }
]
```

Also return top-level object wrapper if easier:

```json
{
  "ticker_map_yaml_draft": "fade_watch:\n  - team: Switzerland\n    kalshi_ticker: ...",
  "pairs": [ "... array above ..." ],
  "blockers": ["Gemini report #5 pending", "..."]
}
```

Operator stages ticker map in a brief before any code merge.
