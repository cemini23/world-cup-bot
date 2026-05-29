# Deep research — Module 6 cross-venue scanner spec

You are a **spec author** for the unbuilt Module 6 **alert-only** cross-venue scanner. Produce an implementation-ready spec the maintainer can code against — no production secrets.

## Scope

Focus context includes:

- `fade_watch_teams`
- `alert_threshold_pp` (5.0)
- PM contract pattern string
- Kalshi pattern hint
- `implementation_status`: not_built

## Research tasks

1. **Kalshi API surface** — Endpoints for market discovery, orderbook/read, auth requirements (read-only vs trade).
2. **Ticker discovery** — How to map PM `condition_id` / team name → Kalshi event + market tickers for WC 2026 advance.
3. **Polling cadence** — Alert-only slow arb: minutes-level poll acceptable; document rate limits.
4. **Rules parser MVP** — Minimum viable equivalence check (title regex + human hash table).
5. **Alert channel** — stdout / JSONL / webhook stub — recommend for OSS v1.

Cross-check: `@world-cup-advance-market-bot-v1` architecture diagram Module 6.

## Output format

Return **only**:

```json
{
  "module": "cross_venue_scanner_v1",
  "scope": "alert_only",
  "recommended_poll_interval_sec": 120,
  "alert_threshold_pp": 5.0,
  "data_sources": {
    "polymarket": ["gamma public-search", "clob midpoint"],
    "kalshi": ["GET /markets", "GET /events"]
  },
  "config_file_proposal": {
    "path": "config/cross_venue.yaml",
    "schema": {
      "pairs": [
        {
          "team": "Switzerland",
          "polymarket_team_slug": "Switzerland",
          "kalshi_event_ticker": "TBD",
          "kalshi_market_ticker": "TBD",
          "rules_hash": "advance_knockout_v1",
          "enabled": true
        }
      ]
    }
  },
  "cli_proposal": "world-cup-bot cross-venue-scan [--json] [--alert-only]",
  "equivalence_rules": [
    "Both resolve YES iff team advances to knockout stage of WC 2026",
    "Reject group-winner-only Kalshi markets"
  ],
  "test_plan": [
    "fixture mock PM + Kalshi mids → alert fires at 6pp",
    "non-equivalent pair → no alert"
  ],
  "risks": ["oracle mismatch", "stale Kalshi book"],
  "dependencies": ["Kalshi API key optional for reads? verify"],
  "estimated_effort_days": 2,
  "open_questions": ["..."]
}
```

Maintainer implements after user GO; ticker map lands in config not wiki.
