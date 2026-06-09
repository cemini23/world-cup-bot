# FIFA World Cup 2026 — tournament kickoff guide

Operator reference for the opening week of the tournament. Architecture and shadow gates remain in [SHADOW.md](../SHADOW.md); command details in [RUNBOOK.md](RUNBOOK.md).

**Opening match:** Mexico vs South Africa — **2026-06-11** (UTC kickoff per [openfootball fixtures](../data/worldcup2026-fixtures.json)).

**Methodology:** [Outlier Weekly Issue 3](https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot) (public launch, 2026-06-03). Tournament-era writeup: [Outlier Weekly Issue 5](https://outlierweekly.substack.com) (World Cup bot — publishing at kickoff).

---

## What this bot does during the tournament

| Module | Tournament role | Default |
|--------|-----------------|---------|
| **Advance LP (1–5)** | Resting limits on *advance to knockout* markets; auto-cancel before kickoff | Shadow or live (operator choice) |
| **Cross-venue (6)** | PM vs Kalshi gap scan; paper ledger; optional Phase C dual-leg | Paper / alert-only |
| **Risk gates (7b)** | Streak sizing + portfolio loss pauses | **On** |
| **Match-shock (8)** | In-play shock recovery on *match* markets | **Off** — separate data plane |

Advance LP and match-shock are **orthogonal**. Do not enable Module 8 live POST on the same wallet as advance LP without explicit sign-off.

---

## Pre-kickoff checklist (all operators)

Run once before your first live or shadow session of the tournament week:

```bash
world-cup-bot preflight
world-cup-bot tournament-ops check
world-cup-bot shadow-status --min-phase 1   # or higher if promoting
world-cup-bot risk-status
```

| Check | Pass | Notes |
|-------|------|-------|
| Fixtures | `tournament-ops` fixtures **pass** | Pull upstream if drift WARN/FAIL |
| Conviction | YAML reviewed; `fade_watch` teams alert-only | Canada, Japan, Scotland, Brazil — review **2026-06-13** |
| Ledger path | One canonical `LEDGER_PATH` / `WC_LEDGER_PATH` | See [SHADOW.md § split-ledger](../SHADOW.md) |
| Geoblock | **PASS** on non-US egress for live POST | US OK for shadow + cross-venue scan |
| Match-shock | WARN until tapes exist | Expected before Module 8 setup |

---

## Shadow operators (recommended first path)

1. Keep `DRY_RUN=true`.
2. Run `plan --record --liquidity-gate` daily through the group stage.
3. Use `watch --record` only after Phase 2 (L2 creds on non-US egress if testing fill path).
4. Interpret PnL honestly:
   - **Quote intents** (`quote_intent_dry_run`) prove wiring — not edge.
   - **Realized PnL** requires `order_fill` rows with `pnl_usd` (typically from `watch --record` + exit discipline) plus optional `rewards sync --record`.
   - Shadow fill counts without `pnl_usd` show **$0 realized** — that is a measurement gap, not proof of zero edge.

Gate: `world-cup-bot shadow-status --min-phase 1` (≥3 UTC days of recorded plans).

---

## Live LP operators (Phase 4 only)

Requirements from [SHADOW.md](../SHADOW.md):

- Non-US egress with `preflight` geoblock **PASS**
- `WC_LIVE_PLAN_ACK=1` after operator sign-off
- `WC_BANKROLL_FROM_WALLET=1` recommended for portfolio gates
- Venue CSV reconcile: `venue-reconcile compare export.csv` (≥20 rows) before scaling

Sizing: respect `MAX_NOTIONAL_PER_MARKET_USD` and wallet collateral caps (`WC_CAP_TO_COLLATERAL`).

---

## Module 8 — match-shock (optional, paper-first)

Enable only after you have a **tape data plane**:

```bash
# 1. Discover WC match markets (when listed on Gamma)
world-cup-bot match-shock-discover --out data/local/match_markets.json

# 2. On egress during live matches — record WS tape
WC_SHOCK_ENABLED=1 world-cup-bot match-shock-record --discovery data/local/match_markets.json

# 3. Paper plan (after tapes exist)
world-cup-bot match-shock-plan --once
```

**Do not** enable `match-shock-plan.timer` until `match-shock-record` produces daily tape files. A missing tape writes `status: skipped` — not a failure.

Live ladder POST requires `WC_MATCH_SHOCK_LIVE=1`, `WC_MATCH_SHOCK_LIVE_ACK=1`, and paper soak. Spec: [MATCH_SHOCK_V1.md](MATCH_SHOCK_V1.md).

---

## Cross-venue arb (Module 6)

Default public path: **Phase A** paper only.

| Phase | Enable when |
|-------|-------------|
| A — scan + paper | Any host; `cross-venue-scan --record` |
| B — manual fills | After alerts; human legs |
| C — auto dual-leg | SHADOW Phase 4 GO + non-US + `WC_CROSS_VENUE_AUTO_EXEC=1` + `WC_CROSS_VENUE_EXEC_ACK=1` |

Refresh pair YAML when slugs drift: `cross-venue-scan --discover-only` → update `config/cross_venue.yaml`.

---

## Match-day posture

On days with kickoffs affecting your quoted teams:

- Confirm `calendar --cancel-window` or timer pulled resting quotes
- Do **not** add new advance-LP size on match day without LP safety review (`scripts/run_wc_lp_safety_reminder.sh`)
- Treat in-play news as adverse-selection risk — the bot does not quote in-play on advance markets by design

---

## Support and context

| Resource | URL |
|----------|-----|
| GitHub | https://github.com/cemini23/world-cup-bot |
| Landing page | https://cemini23.github.io/world-cup-bot/ |
| Issue 3 (architecture) | https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot |
| Issue 5 (tournament) | https://outlierweekly.substack.com |
| Retail PM / WC context | https://github.com/cemini23/Gambling-wiki |

Not financial advice. You run your own keys and infrastructure.
