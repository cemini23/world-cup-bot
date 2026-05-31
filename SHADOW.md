# Shadow mode checklist — before live LP

Run everything with **`DRY_RUN=true`** until Phase 4. Prediction markets can lose capital; LP without cancel discipline around kickoff has burned operators.

## Phase 0 — Install & connectivity

```bash
git clone https://github.com/cemini23/world-cup-bot.git && cd world-cup-bot
cp .env.example .env          # fill keys locally — never commit
pip install -e ".[dev]"
pip install -e ".[live]"        # websockets + py-clob-client (watch / live POST)
world-cup-bot preflight         # geoblock WARN ok in shadow from US
world-cup-bot scan --conviction --liquidity
world-cup-bot ui                # optional dashboard → http://127.0.0.1:8765
```

**Pass criteria:** Gamma returns markets; preflight has no `FAIL` except geoblock when shadowing from US (WARN is OK).

**Optional — 24/7 VPS:** install [deploy/systemd/](deploy/systemd/README.md) (`monitor` profile on any host; `trading` profile on non-US for live POST).

## Phase 1 — Dry-run quote loop (≥3 sessions)

```bash
world-cup-bot plan --liquidity-gate   # inspect intents — no POST
world-cup-bot plan --record --liquidity-gate   # append quote intents to ledger JSONL
world-cup-bot pnl --scope current     # confirm quote_intents rows under current logic_version
world-cup-bot shadow-status --min-phase 1      # gate: prints Ledger path: … + step progress
```

**Pass criteria:**

- [ ] At least **3 separate days** with `plan --record` while `DRY_RUN=true`
- [ ] Conviction rows match your research; `human_review` teams only quote when CLOB depth passes (if `auto_clear_human_review` in `operating.yaml`)
- [ ] No teams inside **cancel window** get quote intents (`calendar --cancel-window`)
- [ ] `cancel --cancel-window` runs on timer / before each `plan` (auto-pull resting quotes)
- [ ] Review `config/conviction.yaml` caps vs bankroll
- [ ] Daily adverse-fill budget understood (`config/operating.yaml` → `risk.max_daily_adverse_fill_usd`; default $500)
- [ ] `shadow-status --min-phase 1` exits 0 (ledger path matches `LEDGER_PATH` / `WC_LEDGER_PATH`)

## Production blind spots (Cemini steal-from)

Before trusting shadow PnL, scan the Cemini **production blind spots** checklist (OSINT wiki: `concepts/production-trading-blind-spots.md`):

| # | Check | WCB mitigation |
|---|-------|----------------|
| 1 | PnL logic versioned | `logic_version` on every ledger row; `pnl --scope current` |
| 2 | Bot journal ≠ venue CSV | **Manual:** export Polymarket trades → `venue-reconcile compare export.csv` (≥20 rows) before Phase 4 |
| 3 | Phantom fills | Reconcile polls order status; never infer fill from timeout |
| 4 | Duplicate fills | Ledger dedup by `order_id` |
| 5 | Silent state drift | WS + 30s REST reconcile in `watch` |
| 6 | Zero intents, no reason | `plan` logs `event=plan_abort abort_reason=…` |
| 7 | 429 rate limit death | `preflight` → `clob_rate_limit` burst probe |

### Negative filter (K88 — selection before speed)

Every `plan` emits `event=negative_filter_summary` with skip buckets (`yaml_skip`, `human_review`, `liquidity_gate`, `mid_band`, …). Aligns with OSINT wiki concept **polymarket-negative-filter-trading** (K88 @myttle) — fix selection tiers in `conviction.yaml` before tuning quote speed.

## Phase 2 — Fill watch (venue reads, still dry)

Requires L2 API creds in `.env` (derive once via py-clob-client).

```bash
world-cup-bot watch --verbose --record
# Ctrl+C after a session; check stats line (messages, trades, fills)
world-cup-bot pnl --scope all --by-version
world-cup-bot rewards sync --record   # optional; requires L2 — enable rewards-sync.timer on VPS
```

**Pass criteria:**

- [ ] WS connects; reconcile loop runs (debug log every 30s if no recovered fills)
- [ ] If you have resting orders elsewhere, fills land in ledger with dedup
- [ ] Understand fill → exit intent path (`fill --team …` dry-run for manual test)
- [ ] Queue depletion / vol pull behavior understood (`config/operating.yaml` fill_handler section)

## Phase 3 — Non-US egress preflight

Order **POST** is geo-blocked from the US. Run from your trading VPS (e.g. EU/Finland):

```bash
# on egress host with DRY_RUN still true first:
world-cup-bot preflight         # geoblock must PASS
world-cup-bot preflight         # L2 GET /data/orders auth probe passes
```

**Pass criteria:**

- [ ] `geoblock` → PASS (not blocked)
- [ ] `clob_auth` → PASS
- [ ] `py_clob_client` → PASS when preparing for live

## Phase 4 — Live pilot (optional, small size)

Only after Phases 0–3. Start with **$500–1K** single-market pilot per bot spec.

```bash
export DRY_RUN=false            # only on egress host
world-cup-bot preflight         # all PASS
world-cup-bot plan --record --liquidity-gate   # posts post-only GTC limits
world-cup-bot watch --record    # fills + REST reconcile + exit POST
```

**Pass criteria:**

- [ ] Kill switch fires on cancel-window fills (test with `calendar --team …`)
- [ ] Exit intents post within 60s of fill
- [ ] Daily `pnl` review; bump `logic_version` on material logic changes
- [ ] **Venue CSV reconcile:** Polymarket account export vs bot ledger (≥20 trades) — `world-cup-bot venue-reconcile compare export.csv`
- [ ] Shadow net PnL ≥ 0 when fills exist (`shadow-status` → shadow_pnl step WARN = review before live)

## Emergency halt (out-of-process)

Cemini prod uses Redis `emergency_stop`; this OSS bot uses **systemd + cancel**:

```bash
# Immediate stop — any host
sudo systemctl stop world-cup-bot-live-plan.timer world-cup-bot-live-plan.service
sudo systemctl stop world-cup-bot-watch.service

# Pull resting quotes (egress host, L2 required)
world-cup-bot cancel --cancel-window --record
world-cup-bot cancel --all-wc --record   # nuclear — review open orders first

# Confirm flat
world-cup-bot orders
```

Set `WC_ALERT_WEBHOOK_URL` for Discord/Slack on kill-switch and cross-venue alerts.

## Quick reference

| Check | Command |
|-------|---------|
| Geoblock | `world-cup-bot preflight` |
| Conviction gate | `world-cup-bot scan --conviction` |
| CLOB depth | `world-cup-bot liquidity-scan` or `scan --liquidity` |
| Cancel window | `world-cup-bot calendar --cancel-window` |
| Cancel orders | `world-cup-bot cancel --cancel-window` |
| Open orders | `world-cup-bot orders` |
| Shadow ledger | `world-cup-bot pnl --scope current` |
| Rewards sync | `world-cup-bot rewards sync --record` (Phase 2+; separate systemd timer) |
| Shadow gate (CI + local) | `world-cup-bot shadow-status --min-phase 1` (exit 1 if pending/blocked; prints ledger path) |
| Daily risk cap | `config/operating.yaml` → `risk.max_daily_adverse_fill_usd` |
| Rate-limit preflight | `world-cup-bot preflight` → `clob_rate_limit` |
| Conviction drift | `world-cup-bot conviction-staleness --notify` |
| Fixture drift | `world-cup-bot fixture-check --notify` |
| UI readiness | `world-cup-bot ui` → **Ready** tab |

## What shadow mode does *not* prove

- Cross-venue Kalshi gaps: `world-cup-bot cross-venue-scan` (alert-only; optional `--loop`)
- Adverse selection under live match news flow
- `$POLY` airdrop eligibility

See [SETUP.md](SETUP.md), [ROADMAP.md](ROADMAP.md), and [CLAUDE.md](CLAUDE.md) for module map and agent rules.

## Sources

- [Source: https://github.com/cemini23/world-cup-bot/blob/main/SHADOW.md]
- [Source: OSINT wiki concepts/production-trading-blind-spots.md — Cemini steal-from checklist]
- [Source: OSINT wiki concepts/polymarket-sports-lp-operating-rules.md]
