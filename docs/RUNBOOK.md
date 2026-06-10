# World Cup Bot — operator runbook

Master command reference by SHADOW phase. Methodology and architecture: [Outlier Weekly Issue 3](https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot). Phase checklist source of truth: [SHADOW.md](../SHADOW.md) in repo root.

Not financial advice. Default is shadow mode (`DRY_RUN=true`). Live order POST requires non-US egress per Polymarket geoblock.

---

## Version pin (update on every material release)

```
WORLD CUP BOT — RUNBOOK SNAPSHOT
Effective: 2026-06-09
Repo: github.com/cemini23/world-cup-bot @ main
Public launch: 2026-06-03 — Outlier Weekly Issue 3

Package: world-cup-bot 0.1.0
Conviction config: config/conviction.yaml version 5
LP logic: wc_advance_lp_v5 (deployed 2026-06-05)
Risk gates: wc_risk_gates_v1 (streak + portfolio; on by default)
Cross-venue paper: wc_cross_venue_paper_v1
Cross-venue auto-exec: wc_cross_venue_exec_v1 (off by default)
Match-shock: wc_match_shock_v1 (off by default; see Module 8 section)
Cross-venue config: config/cross_venue.yaml version 1
Risk gates config: config/risk_gates.yaml version 1
```

If ledger rows show a different `logic_version`, `pnl --scope current` is scoped wrong. Bump [config/strategy_logic_versions.yaml](../config/strategy_logic_versions.yaml) when quoter, fill handler, or calendar logic changes.

Legacy LP logic IDs: `wc_advance_lp_v3`, `wc_advance_lp_v2`, `wc_advance_lp_v1`, `legacy_unversioned`.

---

## Pre-kickoff overlays (K107 / K108 / K109)

Shadow-only — **no live sizing GO** until LP safety DR + shadow soak pass.

| Brief | Config | Bot action |
|-------|--------|------------|
| K107 inflows | `config/k107_liquidity_posture.yaml` | Block volume-headline cap scaling; log cluster repricing on `plan` |
| K108 retail hygiene | `config/k108_retail_hygiene.yaml` | `negative_filter_summary` includes `sports_taker_fee_model_pp`; prefer limit posts |
| K109 semantic routing | `config/wc_semantic_rules.yaml` | `cross-venue-scan` emits `cross_venue_suppressed` for REJ_* pairs |

**Retail hygiene overlay (K108):** sports taker ~0.75% at 50¢; model 1–2% round-trip before widening caps. Fee schedule URL in `k108_retail_hygiene.yaml`. Prefer limit posts (maker-first LP).

**Semantic routing (K109):** registry `config/wc_market_registry.json`. Do not pair PM group-winner with `KXWCGROUPQUAL` (REJ_03). Kalshi macro props log `kalshi_macro_unhedged`.


**K109 P1 calendar hooks:** On 2026-06-27 final group day, `plan` emits `k109_calendar_hook` (third-place GD candidates + completed group matches). Knockout `KXWCGAME` pairing requires PM 90-min rules text — see `k109_calendar_hooks.py`.

**K109 P1 LP routing:** `wc_market_registry.json` (48 teams) drives LP exclusions via `lp_routing.excluded` — rebuild with `python scripts/build_wc_market_registry.py`.

Re-run LP safety DR before `conviction.yaml` edits: `bash scripts/run_wc_lp_safety_reminder.sh`

---

## Phase 0 — Install and discovery

```bash
git clone https://github.com/cemini23/world-cup-bot.git && cd world-cup-bot
cp .env.example .env
pip install -e ".[dev]"
pip install -e ".[live]"
world-cup-bot preflight
world-cup-bot shadow-status --min-phase 0
world-cup-bot risk-status
world-cup-bot scan --conviction --liquidity
world-cup-bot liquidity-scan
world-cup-bot calendar --cancel-window
world-cup-bot ui    # optional → http://localhost:8765
```

| Command | What it does |
|---------|----------------|
| `preflight` | Geoblock probe, Gamma reachability, CLOB auth, rate-limit burst check |
| `shadow-status --min-phase N` | Exit 0 only if SHADOW.md steps for phase N complete; prints ledger path |
| `risk-status [--json]` | Streak sizing mult + portfolio gate state (K102; on by default) |
| `scan --conviction --liquidity` | Gamma advance markets + YAML tiers + CLOB depth column |
| `liquidity-scan` | Depth-only vs `config/operating.yaml` bands |
| `calendar --cancel-window` | Teams inside pre-kickoff cancel window (quoter should stay quiet) |
| `ui` | Read-only localhost dashboard (Ready tab shows who is quotable) |

**Pass:** Gamma returns markets. Preflight has no `FAIL` except geoblock `WARN` when shadowing from the US (expected).

---

## Phase 1 — Dry-run quote loop (≥3 separate days)

```bash
world-cup-bot plan --liquidity-gate
world-cup-bot plan --record --liquidity-gate
world-cup-bot pnl --scope current
world-cup-bot shadow-status --min-phase 1
```

| Command | What it does |
|---------|----------------|
| `plan --liquidity-gate` | Build quote intents from live Gamma mids; no POST when `DRY_RUN=true` |
| `plan --record --liquidity-gate` | Append quote intents to JSONL; tags `logic_version: wc_advance_lp_v5` |
| `pnl --scope current` | PnL for current logic version only |
| `shadow-status --min-phase 1` | Gate before Phase 2; exit 1 if fewer than 3 dry-run days or ledger mismatch |

**Ledger trap:** use one `LEDGER_PATH` / `WC_LEDGER_PATH` for all `plan --record` sessions. Split files make `shadow-status` under-count days.

**Diagnostics:** every `plan` writes `event=negative_filter_summary` with skip counts (`yaml_skip`, `human_review`, `liquidity_gate`, `mid_band`, …). Fix conviction tiers and gates before tuning quote speed.

---

## Phase 2 — Fill watch (venue reads; still dry on POST)

Requires L2 API creds in `.env`.

```bash
world-cup-bot watch --verbose --record
world-cup-bot rewards sync --record
world-cup-bot pnl --scope current
world-cup-bot ledger backfill-pnl --verify
world-cup-bot fill --team <TEAM>   # dry-run single fill / exit path inspect
```

| Command | What it does |
|---------|----------------|
| `watch --record` | WS user channel + REST reconcile; kill-switch; writes `position_exit` PnL |
| `rewards sync --record` | CLOB incentives → `reward_accrual` (L2; portfolio gates count these) |
| `ledger backfill-pnl` | Backfill `position_exit` from history; `--synthesize` for orphan fills |
| `fill --team …` | Inspect exit intent without live POST |

---

## Phase 3 — Non-US egress preflight

Order POST is geo-blocked from the US. Run on non-US host with `DRY_RUN=true` first:

```bash
world-cup-bot preflight    # geoblock PASS; clob_auth PASS
world-cup-bot shadow-status --min-phase 3
```

---

## Phase 4 — Live pilot (optional, small size)

Only after Phases 0–3. Non-US host only.

```bash
export DRY_RUN=false
export WC_LIVE_PLAN_ACK=1    # required for systemd live-plan profile
export WC_BANKROLL_FROM_WALLET=1   # default — portfolio % gates use PM wallet bankroll
world-cup-bot preflight
world-cup-bot risk-status
world-cup-bot cancel --cancel-window
world-cup-bot plan --record --liquidity-gate
world-cup-bot watch --record
world-cup-bot orders
```

| Command | What it does |
|---------|----------------|
| `cancel --cancel-window` | Pull resting quotes for teams entering kickoff window |
| `orders` | Open orders snapshot |

Do not enable `plan --advisor` on timers for initial pilot.

---

## Module 7b — risk gates (K102, on by default)

Streak sizing and portfolio PnL gates in `config/risk_gates.yaml`. Complements the absolute daily cap in `operating.yaml` → `risk.max_daily_adverse_fill_usd`.

```bash
world-cup-bot risk-status
world-cup-bot risk-status --json
```

| Layer | Shadow (`DRY_RUN=true`) | Live |
|-------|-------------------------|------|
| Streak sizing | Scales quote size from ledger fill streaks | Same |
| Portfolio gates | Deferred (no wallet required) | PM wallet bankroll each `plan` |

Live bankroll = free USDC + resting BUY collateral (`WC_BANKROLL_FROM_WALLET=1`, default in `.env.example`). Optional static override: `WC_BANKROLL_USD`. Disable in YAML if you want conviction caps only.

Breach rows use `logic_version: wc_risk_gates_v1` (`risk_gate_breach`, `risk_permanent_halt`).

---

## Cross-venue (Module 6 — scan + optional exec)

```bash
world-cup-bot cross-venue-scan --once --record
world-cup-bot cross-venue-pnl --refresh
world-cup-bot cross-venue-pnl --json
world-cup-bot cross-venue-fill record --team USA --market-type group_winner --pm-price 0.68 --kalshi-price 0.64
world-cup-bot cross-venue-fill reconcile
world-cup-bot cross-venue-exec attempt --force --dry-run   # Phase C sim
# Closed loop (trading VPS): WC_CROSS_VENUE_AUTO_EXEC=1 WC_CROSS_VENUE_EXEC_ACK=1 DRY_RUN=false
world-cup-bot cross-venue-scan --loop --alert-only --record   # paper + auto-exec when env set
world-cup-bot cross-venue-scan --once --record --no-auto-exec  # paper only
```

| Command | What it does |
|---------|----------------|
| `cross-venue-scan --once --record` | PM vs Kalshi gap scan; paper intents to separate JSONL |
| `cross-venue-pnl --refresh` | Mark paper intents vs live gaps |
| `cross-venue-exec attempt` | One-off dual-leg (off unless `WC_CROSS_VENUE_AUTO_EXEC=1` + caps in yaml) |
| `cross-venue-scan --loop --record` | Closed loop: paper + auto-exec when env gates pass |

**Default:** scan + paper ledger only. **Live auto-exec** additionally requires `WC_CROSS_VENUE_EXEC_ACK=1`, preflight PASS, Kalshi + Polymarket creds, and `DRY_RUN=false` on non-US egress. `--alert-only` is output mode only — it does not disable exec.

---

## Research and YAML hygiene

```bash
world-cup-bot research list
world-cup-bot research run weekly-osint-pipeline
world-cup-bot conviction-staleness --notify
world-cup-bot fixture-check --notify
world-cup-bot conviction-patch dr-output.md --stage
```

Research output feeds **manual** YAML edits. It does not replace shadow mode. Shipped `conviction.yaml` is an example (version 5 at snapshot), not picks.

---

## Versioning and post-mortems

```bash
world-cup-bot pnl --scope all --by-version
world-cup-bot venue-reconcile compare polymarket-export.csv
```

Before Phase 4 live: export Polymarket trades and run `venue-reconcile compare` (≥20 rows) to catch bot journal vs venue CSV drift.

When changing quoter/fill/calendar logic mid-tournament:

1. Bump `config/strategy_logic_versions.yaml` → new `version_id`
2. Deploy code
3. Use `pnl --scope all --by-version` for honest era comparison

---

## Optional: systemd (24/7 monitor)

```bash
sudo bash deploy/systemd/install-systemd.sh --install-root /opt/world-cup-bot --profile monitor --enable
```

| Profile | Host | Runs |
|---------|------|------|
| **monitor** | US OK | shadow plan, scan, calendar, cross-venue alerts + paper arb, **tournament-ops**, match-shock discover/plan, daily PnL |
| **trading** | Non-US only | preflight, watch, live plan (Phase 4 — manual), match-shock record/live-plan (manual), cross-venue exec (manual) |

See [deploy/systemd/README.md](../deploy/systemd/README.md).

---

## Module 8 — match-shock (optional, orthogonal to advance LP)

In-play match-market shock recovery (`wc_match_shock_v1`). **Does not gate SHADOW Phases 1–4** for advance LP. Master switch: `config/shock_match.yaml` → `enabled: false`. Historical data uses Polymarket **Data API** (Dome API EOL 2026-04-28).

```bash
world-cup-bot match-shock-discover --out data/local/match_markets.json
world-cup-bot match-shock-export --discovery data/local/match_markets.json
python scripts/shock_backtest/run_bucket_backtest.py data/local/shock_tapes/combined.jsonl --replay

# Live tape during WC (pip install -e ".[live]")
WC_SHOCK_ENABLED=1 world-cup-bot match-shock-record --discovery data/local/match_markets.json

# Paper plan loop + bucket grid
world-cup-bot match-shock-plan --tape data/local/shock_tapes/combined.jsonl
python scripts/shock_backtest/run_bucket_grid.py data/local/shock_tapes/combined.jsonl

# Daily tournament health (fixture + staleness + discover)
world-cup-bot tournament-ops check

# Live POST (egress only — after paper soak + WC_MATCH_SHOCK_LIVE_ACK=1)
world-cup-bot match-shock-post --check-gates
```

Spec: [docs/MATCH_SHOCK_V1.md](../docs/MATCH_SHOCK_V1.md) · backtest: [scripts/shock_backtest/README.md](../scripts/shock_backtest/README.md).

---

## Pre-tournament operator checklist (2026-06-11 kickoff)

Full tournament-week guide: [TOURNAMENT_KICKOFF.md](TOURNAMENT_KICKOFF.md).

Advance LP can run in shadow or live before the opening match (Mexico vs South Africa, **2026-06-11** UTC). **Module 8 match-shock** is a separate stack — enable only after you have tape files from `match-shock-record`.

| When | Action | Verify |
|------|--------|--------|
| **Any host** | `tournament-ops check` + `shadow-status --min-phase 1` | No FAIL rows; one canonical ledger path |
| **Before live POST** | Non-US egress; `preflight` geoblock PASS; SHADOW Phase 4 | `WC_LIVE_PLAN_ACK=1` only after sign-off |
| **Optional Phase C** | Cross-venue dual-leg on non-US: `WC_CROSS_VENUE_AUTO_EXEC=1` + `WC_CROSS_VENUE_EXEC_ACK=1` | `cross-venue-exec attempt --dry-run` gates pass |
| **Before Module 8** | Set `WC_SHOCK_ENABLED=1`; enable `match-shock-record` on egress during matches | Daily tape under `match_shock_tape_dir` |
| **After tapes exist** | `match-shock-plan.timer` or `match-shock-plan --once` | Status file `status: ok` or `skipped` (not `error`) |
| **After paper soak only** | Live ladder POST: `WC_MATCH_SHOCK_LIVE=1` + `WC_MATCH_SHOCK_LIVE_ACK=1` | `match-shock-post --check-gates` |

```bash
world-cup-bot tournament-ops check
world-cup-bot shadow-status --min-phase 1

# Module 8 — only on non-US egress during live matches
# grep -q WC_SHOCK_ENABLED=1 .env || echo 'WC_SHOCK_ENABLED=1' >> .env
# systemctl enable --now world-cup-bot-match-shock-record.service
```

**Do not** enable `match-shock-plan.timer` until `match-shock-record` produces tapes (missing tape → `status: skipped`, exit 0). **Do not** enable `match-shock-live-plan` on the same wallet as advance LP without explicit operator sign-off.

---
## Honest limits

Adverse selection is real. Shadow mode proves wiring, not edge. Reward sync is not alpha. Cross-venue paper ledger is not executed arb. This still fails when news flow front-runs your resting bid.

---

## Links

- Repo: https://github.com/cemini23/world-cup-bot
- Landing: https://cemini23.github.io/world-cup-bot/
- Issue 3 writeup: https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot
- Issue 5 (tournament): https://outlierweekly.substack.com
- Tournament kickoff: docs/TOURNAMENT_KICKOFF.md
- Strategy context: https://github.com/cemini23/Gambling-wiki
