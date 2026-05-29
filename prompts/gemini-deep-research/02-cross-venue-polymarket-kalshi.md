Research **cross-venue probability gaps** between **Polymarket** and **Kalshi** for FIFA World Cup 2026 **advance-to-knockout** (or equivalent group-qualification) contracts. Output feeds an **alert-only scanner** — no auto-hedge or execution recommendations.

**Research goal:** Build a verified map of semantically equivalent PM vs Kalshi contracts for fade-watch teams, compute live probability gaps in percentage points, and flag pairs where raw gap ≥ **5pp** (note whether edge survives Kalshi ~7% profit fee).

**Timeframe:** Current as of {{DATE}}. World Cup 2026 markets only.

**Scope — include:**
- Teams on fade_watch list (see attached context)
- Kalshi public market catalog: `site:kalshi.com World Cup 2026`, Kalshi API docs for market discovery
- Polymarket Gamma / advance market titles for same teams
- Resolution rule comparison: knockout advance vs group winner vs Round of 16 wording
- Prior research flags (Switzerland, England, USA, Croatia book vs Kalshi splits) — **re-verify live**

**Scope — exclude:**
- Auto-arbitrage execution plans
- Non-US inaccessible books unless cited as secondary context only
- Match-level props unless resolution is identical to “advance to knockout”

**Attached bot context:**
```json
{{BOT_CONTEXT}}
```

**Hard rules:**
- If contracts are **not equivalent**, mark `equivalent: false` — do not compute arb gap
- Alert-only v1 — recommend human review, not simultaneous legs
- USA / Mexico: note home-nation liquidity bias; size limits are operator policy

**Output format:**
1. **Executive summary** — how many equivalent pairs found; top 3 gaps
2. **Methodology** — how you matched contracts; fee model
3. **Pair comparison table** — Team | PM question | PM mid | Kalshi ticker | Kalshi implied prob | Equivalent? | Gap (pp) | Alert?
4. **Rules mismatch appendix** — pairs rejected as non-equivalent with reason
5. **Kalshi ticker map draft** — table suitable for `config/cross_venue.yaml`
6. **Sources** (URLs + dates)
7. **Appendix: JSON array** — one object per pair:

```json
{
  "team": "...",
  "polymarket": {"question": "...", "mid": 0.0, "source_url": "..."},
  "kalshi": {"event_ticker": "...", "market_ticker": "...", "implied_prob": 0.0, "source_url": "..."},
  "equivalent": true,
  "gap_pp": 0,
  "alert": false,
  "fee_adjusted_edge_pp": 0,
  "verified_at": "{{DATE}}"
}
```

**Citation requirements:** Minimum **15 sources**. Every mid must link to a market page or API snapshot date. Conflicting Kalshi/PM snapshots — show both timestamps.

**Missing data:** State **unavailable** for tickers you cannot confirm; list as blockers in JSON `blockers` array.
