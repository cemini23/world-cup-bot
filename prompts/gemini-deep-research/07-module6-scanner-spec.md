Research and author an **implementation-ready specification** for a **Module 6 cross-venue alert scanner**: Polymarket vs Kalshi probability gap monitor for FIFA World Cup 2026 advance markets. **Alert-only** — no auto-execution.

**Research goal:** Document Kalshi + Polymarket read APIs, ticker discovery workflow, polling cadence, equivalence rules, config schema, CLI shape, and test plan so a maintainer can implement in ~2 days.

**Timeframe:** Current as of {{DATE}}. APIs and WC 2026 market structure as they exist today.

**Scope — include:**
- Kalshi REST API: market/event discovery, orderbook or mid read, rate limits, auth requirements for **read-only**
- Polymarket Gamma public search + CLOB midpoint patterns (no secrets)
- How to map team name → PM condition_id → Kalshi event/market tickers
- Minimum viable equivalence check (title regex + rules hash table)
- Alert channel recommendation for OSS v1 (stdout / JSONL)
- fade_watch teams from attached context

**Scope — exclude:**
- Production deployment, webhooks with secrets, auto-hedge logic
- Non-public API endpoints

**Attached bot context:**
```json
{{BOT_CONTEXT}}
```

**Output format:**
1. **Architecture overview** (diagram description in prose)
2. **Data sources table** — API | Endpoint | Auth | Rate limit
3. **Ticker discovery playbook** — step-by-step for one example team
4. **Config schema proposal** — `config/cross_venue.yaml` with example pairs
5. **CLI proposal** — e.g. `world-cup-bot cross-venue-scan [--json]`
6. **Equivalence rules** — bullet list of accept/reject criteria
7. **Test plan** — unit scenarios with mock mids
8. **Risks & open questions**
9. **Sources**
10. **Appendix JSON spec object:**

```json
{
  "module": "cross_venue_scanner_v1",
  "scope": "alert_only",
  "recommended_poll_interval_sec": 120,
  "alert_threshold_pp": 5.0,
  "config_file_proposal": {"path": "config/cross_venue.yaml", "schema": {}},
  "cli_proposal": "world-cup-bot cross-venue-scan [--json]",
  "estimated_effort_days": 2,
  "open_questions": []
}
```

**Citation requirements:** Minimum **10 sources** — official Kalshi docs, Polymarket/Gamma docs, GitHub examples if any.

**Missing data:** If Kalshi WC 2026 tickers are not published yet, document discovery strategy and placeholder schema — do not invent tickers without labeling TBD.
