# World Cup Bot — operator runbook

Master command reference by SHADOW phase. Methodology and architecture: [Outlier Weekly Issue 3](https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot). Phase checklist source of truth: [SHADOW.md](../SHADOW.md) in repo root.

Not financial advice. Default is shadow mode (`DRY_RUN=true`). Live order POST requires non-US egress per Polymarket geoblock.

---

## Version pin (update on every material release)

```
WORLD CUP BOT — RUNBOOK SNAPSHOT
Effective: 2026-06-04
Repo: github.com/cemini23/world-cup-bot @ main

Package: world-cup-bot 0.1.0
Conviction config: config/conviction.yaml version 5
LP logic: wc_advance_lp_v4 (deployed 2026-05-30)
Cross-venue paper: wc_cross_venue_paper_v1
Cross-venue auto-exec: wc_cross_venue_exec_v1 (off by default)
Cross-venue config: config/cross_venue.yaml version 1
```

If ledger rows show a different `logic_version`, `pnl --scope current` is scoped wrong. Bump [config/strategy_logic_versions.yaml](../config/strategy_logic_versions.yaml) when quoter, fill handler, or calendar logic changes.

Legacy LP logic IDs: `wc_advance_lp_v3`, `wc_advance_lp_v2`, `wc_advance_lp_v1`, `legacy_unversioned`.

---

## Phase 0 — Install and discovery

```bash
git clone https://github.com/cemini23/world-cup-bot.git && cd world-cup-bot
cp .env.example .env
pip install -e ".[dev]"
pip install -e ".[live]"
world-cup-bot preflight
world-cup-bot shadow-status --min-phase 0
world-cup-bot scan --conviction --liquidity
world-cup-bot liquidity-scan
world-cup-bot calendar --cancel-window
world-cup-bot ui    # optional → http://localhost:8765
```

| Command | What it does |
|---------|----------------|
| `preflight` | Geoblock probe, Gamma reachability, CLOB auth, rate-limit burst check |
| `shadow-status --min-phase N` | Exit 0 only if SHADOW.md steps for phase N complete; prints ledger path |
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
| `plan --record --liquidity-gate` | Append quote intents to JSONL; tags `logic_version: wc_advance_lp_v4` |
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
world-cup-bot fill --team <TEAM>   # dry-run single fill / exit path inspect
```

| Command | What it does |
|---------|----------------|
| `watch --record` | WS user channel + REST reconcile; kill-switch on bad fills |
| `rewards sync --record` | CLOB liquidity incentives into same ledger (L2 required) |
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
world-cup-bot preflight
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

## Cross-venue (Module 6 — alert-first)

```bash
world-cup-bot cross-venue-scan --once --record
world-cup-bot cross-venue-pnl --refresh
world-cup-bot cross-venue-pnl --json
world-cup-bot cross-venue-fill record --team USA --market-type group_winner --pm-price 0.68 --kalshi-price 0.64
world-cup-bot cross-venue-fill reconcile
world-cup-bot cross-venue-exec attempt --force --dry-run   # Phase C sim only
```

| Command | What it does |
|---------|----------------|
| `cross-venue-scan --once --record` | PM vs Kalshi gap alerts; paper intents to separate JSONL |
| `cross-venue-pnl --refresh` | Mark paper intents vs live gaps |
| `cross-venue-exec attempt` | Auto dual-leg (off unless `WC_CROSS_VENUE_AUTO_EXEC=1` + caps in yaml) |

Default path is **alert + paper ledger**, not auto execution.

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
| **monitor** | US OK | shadow plan, scan, calendar, cross-venue alerts, daily PnL |
| **trading** | Non-US only | live plan (manual enable after Phase 4) |

See [deploy/systemd/README.md](../deploy/systemd/README.md).

---

## Honest limits

Adverse selection is real. Shadow mode proves wiring, not edge. Reward sync is not alpha. Cross-venue paper ledger is not executed arb. This still fails when news flow front-runs your resting bid.

---

## Links

- Repo: https://github.com/cemini23/world-cup-bot
- Landing: https://cemini23.github.io/world-cup-bot/
- Issue 3 writeup: https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot
- Strategy context: https://github.com/cemini23/Gambling-wiki
