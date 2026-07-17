# World Cup Bot

[![CI](https://img.shields.io/badge/CI-passing-brightgreen?logo=githubactions&logoColor=white&updated=20260613T211354Z)](https://github.com/cemini23/world-cup-bot/actions/workflows/ci.yml)
<!-- ci-badge-updated:2026-06-13T21:13:54Z -->
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**World Cup Bot** — open-source liquidity provision for **FIFA World Cup 2026** *advance to knockout* markets on [Polymarket](https://polymarket.com), with **Polymarket vs [Kalshi](https://kalshi.com)** cross-venue gap scan, paper ledger, and **optional gated dual-leg auto-exec** (Phase C, off by default). Landing page: [cemini23.github.io/world-cup-bot](https://cemini23.github.io/world-cup-bot/).

**CI:** passing · **Status:** **v1 public** — MIT OSS, **shadow-first** (`DRY_RUN=true`). **FIFA World Cup 2026** opening match **2026-06-11**. Tournament guide: [docs/TOURNAMENT_KICKOFF.md](docs/TOURNAMENT_KICKOFF.md). Announced in [Outlier Weekly Issue 3](https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot); tournament writeup in [Outlier Weekly Issue 5](https://outlierweekly.substack.com). Logic versions: `wc_advance_lp_v8` (advance LP) · `wc_risk_gates_v1` (streak + portfolio gates) · `wc_cross_venue_paper_v1` / `wc_cross_venue_exec_v1` (arb) · `wc_match_shock_v1` (in-play shock, **off by default**). Operator map: [docs/RUNBOOK.md](docs/RUNBOOK.md) · Gates: [SHADOW.md](SHADOW.md) · Roadmap: [ROADMAP.md](ROADMAP.md).

## Public launch (2026-06-03)

World Cup Bot is **open source** for operators who run their own infrastructure. Fork the repo, shadow-test with your API keys, and promote to live LP only after the phased checklist passes. This project is **not** a hosted service, managed account, or performance guarantee.

| Step | Action |
|------|--------|
| 1 | `git clone` → `cp .env.example .env` → `pip install -e ".[dev]"` → `bash scripts/shadow_setup.sh` (or `world-cup-bot preflight`) |
| 2 | Complete [SHADOW.md](SHADOW.md) Phases 0–3 with `DRY_RUN=true` (`plan --record --liquidity-gate`) |
| 3 | Keep **one** `LEDGER_PATH` / `WC_LEDGER_PATH` for every recorded session ([SHADOW.md](SHADOW.md) § split-ledger trap) |
| 4 | Read [Outlier Weekly Issue 3](https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot) for architecture; use [Gambling-wiki](https://github.com/cemini23/Gambling-wiki) for retail WC / PM context |

Optional health check before kickoff: `world-cup-bot tournament-ops check` (fixtures, conviction staleness, cross-venue discovery, match-shock readiness). Full tournament-week checklist: [docs/TOURNAMENT_KICKOFF.md](docs/TOURNAMENT_KICKOFF.md).

## What it does (v1)

| Module | Scope |
|--------|--------|
| **Scanner (1)** | Gamma discovery; live mids, spreads, reward params |
| **Conviction LP (2)** | YAML tiers; resting limits on research-backed teams; bilateral mode above ~90¢ |
| **Quoter (3)** | Post-only GTC limits; cancel-replace before submit; calendar auto-cancel |
| **Fill handler (4)** | WS user channel + REST reconcile; kill-switch + queue pull + vol cooldown; exit within ~60s |
| **Calendar guard (5)** | CC0 fixtures; cancel window before kickoff |
| **Cross-venue (6)** | PM vs Kalshi gap scan (15 cohort pairs); **Phase A** paper ledger (`--record`); **Phase B** manual fills; **Phase C** gated auto-exec; optional webhook |
| **Ledger (7)** | Versioned JSONL — quotes, fills, cancels, **`position_exit`** round-trips, **rewards sync** (`reward_accrual`) |
| **Risk gates (7b)** | Streak sizing + portfolio PnL gates — **on by default**; live bankroll from PM wallet (`risk-status`) |
| **Liquidity gate** | Public CLOB `/book` depth vs `config/operating.yaml`; asymmetric bid/ask band floors; optional auto-clear `human_review` (default off) |
| **Optional advisor** | `plan --advisor` — LLM overlay; off by default |
| **Optional UI** | `ui` — read-only localhost dashboard (port 8765) |
| **Research CLI** | Gemini Deep Research + agent JSON bundles in `prompts/` |
| **Match-shock (8)** | In-play shock recovery (orthogonal to advance LP) — discover, Data API export, live WS tape, paper/live plan, gated POST; **disabled by default** — [`docs/MATCH_SHOCK_V1.md`](docs/MATCH_SHOCK_V1.md) |

Prices, spreads, and kickoff times come from **Gamma + CLOB at runtime** — nothing hardcoded.

Current risk posture: `Canada`, `Japan`, `Scotland`, and `Brazil` are **`fade_watch`** (alert-only) in `config/conviction.yaml` — K96 review **2026-06-04** confirmed; next review **2026-06-13** or after June friendlies.

### Go-live safety

- Auto-cancel resting quotes when teams enter the pre-kickoff window (`plan`, `watch`, calendar timer)
- Cancel-replace stale quotes before new posts
- Kill-switch on cancel-window fills → halt team + pull quotes
- **Persistent kill-switch** — `trading_halt` / `trading_halt_clear` ledger events survive plan cron restarts
- **Live POST preflight gate** — `submit_quotes` runs full preflight; `submit_exit` uses a minimal key/deps gate (no Gamma/burst) so kill-switch flattens are not blocked by discovery outages when `DRY_RUN=false`
- Queue depletion + volatility pull in fill watch (configurable in `operating.yaml`)
- Optional operator alerts: `WC_ALERT_WEBHOOK_URL` (Discord/Slack HTTPS only)
- **`MAX_NOTIONAL_PER_MARKET_USD`** — env hard ceiling on per-market quote size (min with YAML caps)
- **Risk gates (K102)** — streak-based quote scaling + portfolio % loss pauses (`config/risk_gates.yaml`; portfolio gates defer in `DRY_RUN`)
- **`WC_BANKROLL_FROM_WALLET=1`** — live % gates use PM USDC + open BUY collateral (default in `.env.example`)
- Live plan timer requires **`WC_LIVE_PLAN_ACK=1`** in `.env` after SHADOW Phase 4 (see `deploy/systemd/README.md`)

## What it is not

- Not financial advice
- Not guaranteed edge — LP rewards + fill discipline; adverse selection is real
- Not a hosted service — you run it locally or on your own VPS
- **Not connected to any operator production stack** — fork runs on **your** credentials only

## Quick start

```bash
git clone https://github.com/cemini23/world-cup-bot.git
cd world-cup-bot
cp .env.example .env   # fill in your own Polymarket keys
pip install -e ".[dev]"
pip install -e ".[live]" # watch + live POST (websockets, py-clob-client-v2)

# Phase 0 — connectivity
world-cup-bot preflight
world-cup-bot shadow-status --min-phase 0   # prints ledger path + step progress
world-cup-bot risk-status                    # streak mult + portfolio gate state

# Discover + plan (shadow)
world-cup-bot scan --conviction --liquidity  # conviction + CLOB depth column
world-cup-bot liquidity-scan                  # depth-only vs operating.yaml
world-cup-bot calendar --cancel-window
world-cup-bot plan --record --liquidity-gate  # DRY_RUN=true default; ledger audit when --record

# Operator automation (optional)
world-cup-bot conviction-staleness --notify
world-cup-bot fixture-check --notify
world-cup-bot conviction-patch dr-output.md --stage

# Fills + PnL
world-cup-bot watch --verbose --record   # needs L2 API creds
world-cup-bot rewards sync --record      # CLOB liquidity rewards → ledger (L2 required)
world-cup-bot pnl --scope current
world-cup-bot ledger backfill-pnl --verify # position_exit from exit_intent; --synthesize for orphan fills

# Operator
world-cup-bot cancel --cancel-window
world-cup-bot orders
world-cup-bot cross-venue-scan --once --record   # paper arb intents on alerts
world-cup-bot cross-venue-pnl --refresh          # MTM vs live gaps
world-cup-bot cross-venue-fill record --team USA --market-type group_winner --pm-price 0.68 --kalshi-price 0.64
world-cup-bot cross-venue-fill reconcile         # match intents vs manual fills
world-cup-bot cross-venue-exec attempt --force --dry-run  # Phase C sim (caps apply)
world-cup-bot venue-reconcile compare polymarket-export.csv  # blind-spot #2
world-cup-bot ui                         # optional dashboard → http://localhost:8765

# Pre-kickoff health (fixtures, staleness, cross-venue, match-shock tapes)
world-cup-bot tournament-ops check

# Module 8 — match-shock (paper-first; live tape needs WC_SHOCK_ENABLED=1)
world-cup-bot match-shock-discover --out data/local/match_markets.json
world-cup-bot match-shock-export --discovery data/local/match_markets.json
WC_SHOCK_ENABLED=1 world-cup-bot match-shock-record --discovery data/local/match_markets.json
```

More commands: `world-cup-bot --help` · research modes: `world-cup-bot research list` · shock backtest: `scripts/shock_backtest/README.md`

Requires a Polymarket account with CLOB API access. Cross-venue **scanning** uses public Gamma + Kalshi reads (no Kalshi login required). **Phase C auto-exec** needs Kalshi trading credentials + Polymarket L2 on non-US egress.

**Calendar guard (Module 5)** uses vendored [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) fixtures (`data/worldcup2026-fixtures.json`, CC0) — not live prices. See `data/DATA_ATTRIBUTION.md`.

## Shadow → live

Follow [SHADOW.md](SHADOW.md):

1. **≥3 days** of `plan --record --liquidity-gate` with `DRY_RUN=true`
2. `watch --record` with L2 creds
3. Non-US egress preflight (`geoblock` PASS)
4. Live pilot — small size, manual enable only

Gate check: `world-cup-bot shadow-status --min-phase 1` (exit 1 if steps pending; prints resolved ledger path).

### Cross-venue arb (Module 6)

Three phases — default shadow path is **scan + paper only**; live dual-leg POST is explicit opt-in.

| Phase | What | Orders? |
|-------|------|---------|
| **A** | `cross-venue-scan --record` → paper intents in `cross_venue_arb_ledger.jsonl` | No |
| **B** | `cross-venue-fill record\|import-csv\|reconcile` — manual fill bridge | Human legs only |
| **C** | `cross-venue-exec attempt` or scan loop with auto-exec env | Yes — dual-leg when gated |

```bash
world-cup-bot cross-venue-scan --once --record
world-cup-bot cross-venue-pnl --refresh    # mark-to-market vs current gaps
world-cup-bot cross-venue-pnl --json       # scriptable summary
world-cup-bot cross-venue-exec attempt --force --dry-run   # sim gates + sizing
```

**Phase C live loop** (non-US VPS, after paper soak + SHADOW Phase 4 GO):

```bash
# .env — both required
WC_CROSS_VENUE_AUTO_EXEC=1
WC_CROSS_VENUE_EXEC_ACK=1
DRY_RUN=false

world-cup-bot cross-venue-scan --loop --alert-only --record   # one auto attempt per alert cycle
# or: systemctl enable --now world-cup-bot-cross-venue-exec.service
```

Disable auto-exec for a single run: `--no-auto-exec`. Pilot caps in `config/cross_venue.yaml` → `auto_arb:` (default 100 USD/leg, 500 USD/day). Paper defaults in `paper_arb:` (500 USD notional, 3600s dedup).

## 24/7 on a VPS

Optional [systemd units](deploy/systemd/README.md):

| Profile | Host | Runs |
|---------|------|------|
| **monitor** | US OK | cross-venue scan + **paper `--record`**, shadow plan (`--liquidity-gate`), scan, calendar, discover, daily PnL, conviction-staleness, fixture-check |
| **trading** | Non-US only | preflight, watch, live plan (Phase 4), **cross-venue exec loop** (Phase C — manual enable) |

**PnL vs rewards:** `pnl-daily.timer` runs `pnl --scope current` on the shadow ledger (no L2). `rewards-sync.timer` is installed but **not** auto-enabled — enable after Phase 2 when L2 creds exist.

```bash
sudo bash deploy/systemd/install-systemd.sh --install-root /opt/world-cup-bot --profile monitor --enable
```

See [SETUP.md](SETUP.md) for environment variables and geoblock notes. **Contributors:** [CONTRIBUTING.md](CONTRIBUTING.md) · **Agents:** [CLAUDE.md](CLAUDE.md) · **Roadmap:** [ROADMAP.md](ROADMAP.md).

## Security

- Never commit `.env`, private keys, or wallet seed phrases
- See [SECURITY.md](SECURITY.md) for what stays out of this repo

## Related

- Methodology newsletter: [Outlier Weekly Issue 3](https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot) (launch) · [Issue 5](https://outlierweekly.substack.com) (tournament kickoff) · [Outlier Weekly home](https://outlierweekly.substack.com)
- Operator runbook: [docs/RUNBOOK.md](docs/RUNBOOK.md)
- **Retail / bankroll lens:** [Gambling-wiki](https://github.com/cemini23/Gambling-wiki) — WC contract types, books vs PM, CLV ([prediction-markets crossover](https://github.com/cemini23/Gambling-wiki/blob/main/wiki/concepts/prediction-markets-crossover.md)). **This repo** = bot/LP automation only.
- YouTube: [@Cemini23](https://www.youtube.com/@Cemini23)
- Agent meta-wiki: [cemini-claude-code-CCC](https://github.com/cemini23/cemini-claude-code-CCC)
- Agent toolkit: [vet](https://github.com/cemini23/vet) · [wikilint](https://github.com/cemini23/wikilint) · [phase0](https://github.com/cemini23/phase0) · [agent-toolkit-demo](https://github.com/cemini23/agent-toolkit-demo)
- More Cemini repos: [all public →](https://github.com/orgs/cemini23/repositories?q=visibility%3Apublic)


## Support

Voluntary tips fund open research and tooling. **Donation-only addresses** — not trading or production wallets.

| Chain family | Address |
|--------------|---------|
| **EVM** (Ethereum, Polygon, Base, Arbitrum, …) | `0x444C5C2eC439E0382aa5a17F70313c536BcC5D58` |
| **Solana / SVM** | `J4zNn4hK9jTrKBFY8sbAGJHLoZvXvQf4B9pQSbSrocZE` |
| **Polymarket** (referral) | [polymarket.com/?r=Cemini23](https://polymarket.com/?r=Cemini23) |


## License

MIT — see [LICENSE](LICENSE).
