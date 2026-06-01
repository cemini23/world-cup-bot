# World Cup Bot

[![CI](https://img.shields.io/github/actions/workflow/status/cemini23/world-cup-bot/ci.yml?branch=main&label=CI)](https://github.com/cemini23/world-cup-bot/actions/workflows/ci.yml)
<!-- ci-badge-updated:2026-06-01T04:19:04Z -->
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**World Cup Bot** — open-source liquidity provision for **FIFA World Cup 2026** *advance to knockout* markets on [Polymarket](https://polymarket.com), with **Polymarket vs [Kalshi](https://kalshi.com)** cross-venue gap alerts (alert-only). Landing page: [cemini23.github.io/world-cup-bot](https://cemini23.github.io/world-cup-bot/).

**CI:** passing · **Status:** feature-complete v1 — **shadow mode first** (`DRY_RUN=true`). Public launch tied to [Outlier Weekly](https://outlierweekly.substack.com) Issue 3 (2026-06-03). Logic version: `wc_advance_lp_v4` · paper arb: `wc_cross_venue_paper_v1` · exec: `wc_cross_venue_exec_v1`. See [ROADMAP.md](ROADMAP.md) for open operator items.

## What it does (v1)

| Module | Scope |
|--------|--------|
| **Scanner (1)** | Gamma discovery; live mids, spreads, reward params |
| **Conviction LP (2)** | YAML tiers; resting limits on research-backed teams; bilateral mode above ~90¢ |
| **Quoter (3)** | Post-only GTC limits; cancel-replace before submit; calendar auto-cancel |
| **Fill handler (4)** | WS user channel + REST reconcile; kill-switch + queue pull + vol cooldown; exit within ~60s |
| **Calendar guard (5)** | CC0 fixtures; cancel window before kickoff |
| **Cross-venue (6)** | PM vs Kalshi gap alerts (15 cohort pairs); **paper arb ledger** (`--record`, `cross-venue-pnl`); optional webhook |
| **Ledger (7)** | Versioned JSONL — quotes, fills, cancels, **rewards sync** (separate cron unit) |
| **Liquidity gate** | Public CLOB `/book` depth vs `config/operating.yaml`; asymmetric bid/ask band floors; auto-clear `human_review` when configured |
| **Optional advisor** | `plan --advisor` — LLM overlay; off by default |
| **Optional UI** | `ui` — read-only localhost dashboard (port 8765) |
| **Research CLI** | Gemini Deep Research + agent JSON bundles in `prompts/` |

Prices, spreads, and kickoff times come from **Gamma + CLOB at runtime** — nothing hardcoded.

K91 pre-kickoff risk posture (2026-05-31): `Canada`, `Japan`, `Scotland`, and `Brazil` are currently forced `fade_watch` (alert-only) in `config/conviction.yaml` pending the scheduled LP safety re-run.

### Go-live safety

- Auto-cancel resting quotes when teams enter the pre-kickoff window (`plan`, `watch`, calendar timer)
- Cancel-replace stale quotes before new posts
- Kill-switch on cancel-window fills → halt team + pull quotes
- Queue depletion + volatility pull in fill watch (configurable in `operating.yaml`)
- Optional operator alerts: `WC_ALERT_WEBHOOK_URL` (Discord/Slack JSON POST)

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
pip install -e ".[live]" # watch + live POST (websockets, py-clob-client)

# Phase 0 — connectivity
world-cup-bot preflight
world-cup-bot shadow-status --min-phase 0   # prints ledger path + step progress

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
```

More commands: `world-cup-bot --help` · research modes: `world-cup-bot research list`

Requires a Polymarket account with CLOB API access. Kalshi alerts need separate Kalshi API credentials (optional for LP-only mode).

**Calendar guard (Module 5)** uses vendored [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) fixtures (`data/worldcup2026-fixtures.json`, CC0) — not live prices. See `data/DATA_ATTRIBUTION.md`.

## Shadow → live

Follow [SHADOW.md](SHADOW.md):

1. **≥3 days** of `plan --record --liquidity-gate` with `DRY_RUN=true`
2. `watch --record` with L2 creds
3. Non-US egress preflight (`geoblock` PASS)
4. Live pilot — small size, manual enable only

Gate check: `world-cup-bot shadow-status --min-phase 1` (exit 1 if steps pending; prints resolved ledger path).

### Cross-venue paper arb (Phase A)

When a PM↔Kalshi gap crosses the alert threshold, `--record` appends a **paper intent** to `data/local/cross_venue_arb_ledger.jsonl` (override with `WC_CROSS_VENUE_LEDGER_PATH`). No orders are placed.

```bash
world-cup-bot cross-venue-scan --once --record
world-cup-bot cross-venue-pnl --refresh    # mark-to-market vs current gaps
world-cup-bot cross-venue-pnl --json       # scriptable summary
```

Defaults in `config/cross_venue.yaml` → `paper_arb:` (500 USD notional, 3600s dedup per pair). **Phase B** (manual fills + reconcile): `cross-venue-fill record|import-csv|reconcile`. **Phase C** (auto dual-leg, off by default): set `WC_CROSS_VENUE_AUTO_EXEC=1` + `DRY_RUN=false` on non-US VPS, then `cross-venue-exec attempt`. Pilot caps in `auto_arb:` block.

## 24/7 on a VPS

Optional [systemd units](deploy/systemd/README.md):

| Profile | Host | Runs |
|---------|------|------|
| **monitor** | US OK | cross-venue alerts + **paper arb `--record`**, shadow plan (`--liquidity-gate`), scan, calendar, discover, daily PnL, conviction-staleness, fixture-check |
| **trading** | Non-US only | preflight, watch, live plan (Phase 4 — manual enable) |

**PnL vs rewards:** `pnl-daily.timer` runs `pnl --scope current` on the shadow ledger (no L2). `rewards-sync.timer` is installed but **not** auto-enabled — enable after Phase 2 when L2 creds exist.

```bash
sudo bash deploy/systemd/install-systemd.sh --install-root /opt/world-cup-bot --profile monitor --enable
```

See [SETUP.md](SETUP.md) for environment variables and geoblock notes. **Contributors / AI agents:** [CLAUDE.md](CLAUDE.md) · **Open items:** [ROADMAP.md](ROADMAP.md).

## Security

- Never commit `.env`, private keys, or wallet seed phrases
- See [SECURITY.md](SECURITY.md) for what stays out of this repo

## Related

- Methodology newsletter: [Outlier Weekly](https://outlierweekly.substack.com)
- **Retail / bankroll lens:** [Gambling-wiki](https://github.com/cemini23/Gambling-wiki) — WC contract types, books vs PM, CLV ([prediction-markets crossover](https://github.com/cemini23/Gambling-wiki/blob/main/wiki/concepts/prediction-markets-crossover.md)). **This repo** = bot/LP automation only.
- YouTube: [@Cemini23](https://www.youtube.com/@Cemini23)
- Agent meta-wiki: [cemini-claude-code-CCC](https://github.com/cemini23/cemini-claude-code-CCC)
- Agent toolkit: [vet](https://github.com/cemini23/vet) · [wikilint](https://github.com/cemini23/wikilint) · [phase0](https://github.com/cemini23/phase0) · [agent-toolkit-demo](https://github.com/cemini23/agent-toolkit-demo)
- More Cemini repos: [all public →](https://github.com/orgs/cemini23/repositories?q=visibility%3Apublic)

## License

MIT — see [LICENSE](LICENSE).
