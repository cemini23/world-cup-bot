# Setup

## Prerequisites

- Python 3.11+
- Polymarket account with CLOB API access (for live LP only)
- US geoblock: check `GET https://polymarket.com/api/geoblock` from your egress IP before live orders

**Gamma reads vs trading:** `gamma-api.polymarket.com` public-search works from a US IP when the client sends a normal `User-Agent` (bare Python `urllib` gets HTTP 403 from Cloudflare). **Order POST** is geo-blocked from the US — use non-US egress (see repo geoblock notes) for live quotes.

## Environment

Copy `.env.example` → `.env` and fill values locally. The `world-cup-bot` CLI loads `.env` from the repo root on startup (shell env wins; set `WC_SKIP_DOTENV=1` to disable).

| Variable | Required | Notes |
|----------|----------|-------|
| `POLYMARKET_PRIVATE_KEY` | LP mode | CLOB signing key |
| `POLYMARKET_FUNDER_ADDRESS` | LP mode | Proxy/funder address |
| `POLYMARKET_API_KEY` | `watch` | L2 API key (UUID) — not Builder keys |
| `POLYMARKET_API_SECRET` | `watch` | L2 API secret |
| `POLYMARKET_API_PASSPHRASE` | `watch` | L2 API passphrase |
| `DRY_RUN` | yes | Keep `true` until you have shadow-tested |
| `LEDGER_PATH` / `WC_LEDGER_PATH` | recommended | **Same path** for manual CLI and systemd — see [SHADOW.md](SHADOW.md) split-ledger section |
| `WC_LOAD_POLYMARKET_ENV` | optional | Set `1` if L2 keys live in `.env-polymarket` (Cemini layout) |
| `WC_SKIP_DOTENV` | optional | Set `1` to skip auto-loading repo-root `.env` (CI/tests) |
| `MAX_NOTIONAL_PER_MARKET_USD` | no | Hard ceiling per market (minimum with `conviction.yaml` caps; default `2000`) |
| `WC_BANKROLL_FROM_WALLET` | no | Default `1` — portfolio gate % limits use live PM USDC + open BUY lock (see `config/risk_gates.yaml`) |
| `WC_BANKROLL_USD` | no | Optional static bankroll override; unset = wallet sync when live |
| `WC_LIVE_PLAN_ACK` | live timer | Set to `1` in `.env` before enabling `world-cup-bot-live-plan.timer` |
| `WC_ALERT_WEBHOOK_URL` | no | Discord/Slack HTTPS webhook for operator alerts |
| `WC_WIKI_ENFORCEMENT` | no | Set `1` to block live POST when intents violate `operating.yaml` wiki rules |
| `MIN_HOURS_BEFORE_KICKOFF` | no | Calendar guard cancel threshold (default `10`) |

Derive L2 creds once from your private key (`py-clob-client-v2` `create_or_derive_api_creds()`), then store the three values above in `.env`.

## Reproducible installs

Optional pinned deps for CI/VPS parity:

```bash
pip install -r requirements-lock.txt
pip install -e ".[live]"   # or pip install -e ".[dev]" for pytest/ruff
```

Regenerate after bumping `pyproject.toml` optional extras. CI runs `python scripts/check_requirements_lock.py`.

Shadow bootstrap: `bash scripts/shadow_setup.sh` (Phase 0 preflight + plan --record).

## Risk gates (K102 — on by default)

Streak sizing and portfolio PnL gates live in **`config/risk_gates.yaml`** (both **enabled** out of the box).

| Layer | Shadow (`DRY_RUN=true`) | Live |
|-------|-------------------------|------|
| Streak sizing | Scales quote size from ledger fill streaks | Same |
| Portfolio gates | **Deferred** until go-live (no wallet needed) | **PM wallet bankroll** each `plan` |

```bash
world-cup-bot risk-status          # streak mult + gate state
world-cup-bot risk-status --json
```

Live bankroll = free USDC + resting BUY collateral (`WC_BANKROLL_FROM_WALLET=1`, default in `.env.example`). Set `WC_BANKROLL_USD` only if you want a fixed reference instead of wallet sync. Disable layers in `config/risk_gates.yaml` if you prefer bare conviction caps only.

**Travel burden:** `config/travel_burden.yaml` applies a **small** notional haircut (max 6%) when a team's FIFA base camp is far from group-stage venues (data in `data/wc2026-base-camps.yaml`). Does not change conviction tiers — only quote size in `plan`.

## Live fill watch (Module 4)

```bash
pip install -e ".[live]"   # websockets dependency
world-cup-bot watch --verbose --record
```

Subscribes to `wss://ws-subscriptions-clob.polymarket.com/ws/user` for WC advance **condition IDs** discovered via Gamma. On `TRADE` / `MATCHED`, parses **maker** legs → fill handler → optional ledger.

Pair with periodic REST `/data/trades` reconciliation (every 30s in `watch`) before live capital. WebSocket alone can miss silent fills — run both in production.

## Pre-flight (before live LP)

```bash
world-cup-bot preflight
```

Checks: geoblock, Gamma public-search, CLOB `/time`, L2 creds, optional `GET /data/orders` auth probe, `py-clob-client-v2` when `DRY_RUN=false`.

**Geoblock note:** Polymarket’s API may label a non-US VPS (e.g. Helsinki) with a different country code. If `clob_auth` passes in shadow mode, preflight treats egress as safe — verify with your own smoke `plan` before live size.

```bash
pip install -e ".[live]"   # py-clob-client-v2 + websockets + eth-account
```

## Live POST (DRY_RUN=false)

```bash
pip install -e ".[live]"   # py-clob-client-v2 + websockets + eth-account
world-cup-bot preflight      # must pass geoblock + deps from non-US egress
world-cup-bot plan           # posts post-only GTC limits when DRY_RUN=false
```

Requires `POLYMARKET_PRIVATE_KEY`, L2 API creds, and `POLYMARKET_FUNDER_ADDRESS` for proxy wallets. **Order POST is geo-blocked from the US.**

## Calendar guard

Kickoff times from bundled CC0 fixtures (`data/worldcup2026-fixtures.json`), not Polymarket:

```bash
world-cup-bot calendar --team Turkey
world-cup-bot calendar --cancel-window --min-hours 10
world-cup-bot cancel --cancel-window   # pull resting quotes for teams near kickoff
world-cup-bot orders                   # list open WC advance orders (L2 auth)
world-cup-bot fixture-check --notify   # diff vendored fixtures vs openfootball upstream
```

Refresh if FIFA reschedules — see `data/DATA_ATTRIBUTION.md`. Use `fixture-check --apply` only after reviewing diffs.

## Liquidity gate (CLOB /book)

Public order-book depth vs `config/operating.yaml` — no auth required:

```bash
world-cup-bot liquidity-scan              # all eligible advance markets
world-cup-bot liquidity-scan --team Morocco
world-cup-bot scan --conviction --liquidity   # conviction table + PASS/FAIL depth column
world-cup-bot plan --liquidity-gate         # block/auto-clear human_review from depth
```

Defaults (WC advance tuning): bid band ≥ **$50**, ask band ≥ **$15**, combined book ≥ **$150**. `auto_clear_human_review` defaults **false** — depth alone does not clear `human_review` in conviction YAML unless you opt in via `config/operating.yaml`.

Per-market notional caps: **`config/conviction.yaml`** (`limits` + `per_team`) with a hard ceiling from **`MAX_NOTIONAL_PER_MARKET_USD`** in `.env` (whichever is lower).

## Shadow gate

```bash
world-cup-bot shadow-status --min-phase 1
```

Prints `Ledger path: …`, step progress, and ledger stats. Exit code **1** if any step through `min_phase` is `pending` or `blocked`. Use `--json` for automation.

## Conviction maintenance

```bash
world-cup-bot conviction-staleness --notify   # mid drift vs conviction tiers; optional webhook
world-cup-bot conviction-patch dr.md --stage  # DR JSON → staged YAML snippet (manual merge)
```

## Modes

| Mode | Command | Posts orders? |
|------|---------|---------------|
| Shadow | `DRY_RUN=true` | No — logs intended quotes |
| Fill watch | `world-cup-bot watch` | No — ingests venue fills over WS |
| Live LP | `DRY_RUN=false` | Yes — limit orders only |

See [SHADOW.md](SHADOW.md) for the phased go-live checklist (≥3 dry-run days, watch, egress preflight).

## Kalshi / cross-venue (Module 6)

Module 6 **scans** PM vs Kalshi gaps using public Gamma + Kalshi market APIs — no Kalshi login required for scan/discover/paper.

**Execution is phased and gated:**

| Phase | Mode | Posts orders? |
|-------|------|---------------|
| A | `cross-venue-scan --record` | No — paper intents only |
| B | `cross-venue-fill record\|reconcile` | Human-recorded legs |
| C | `WC_CROSS_VENUE_AUTO_EXEC=1` + `WC_CROSS_VENUE_EXEC_ACK=1` + `DRY_RUN=false` | Yes — auto dual-leg on alerts |

```bash
world-cup-bot cross-venue-scan              # scan config pairs once
world-cup-bot cross-venue-scan --discover-only   # new PM↔Kalshi pairs for YAML
world-cup-bot cross-venue-scan --loop       # poll every poll_interval_sec (YAML)
world-cup-bot cross-venue-scan --alert-only # compact stdout (alerts + slug warnings only)
world-cup-bot cross-venue-scan --loop --record --no-auto-exec   # paper loop, no POST
world-cup-bot cross-venue-exec attempt --dry-run   # sim Phase C gates + sizing
```

`--alert-only` controls **CLI output verbosity** — it does not disable Phase C auto-exec when `WC_CROSS_VENUE_AUTO_EXEC=1`.

When Polymarket slugs change or new WC markets appear, run `--discover-only`, review `rules_hash`, paste rows into `config/cross_venue.yaml`.

Phase C requires Kalshi trading credentials in `.env` (see `.env.example`) plus Polymarket L2 on **non-US egress**. See [deploy/systemd/README.md](deploy/systemd/README.md) for `world-cup-bot-cross-venue-exec.service`.

## Deep research prompts

**Gemini Deep Research** (long-form cited reports): `prompts/gemini-deep-research/`

```bash
world-cup-bot research gemini group-conviction --group B
world-cup-bot research gemini cross-venue
```

Copy output → **gemini.google.com** → Deep Research → Start research.

**Agent JSON** (Cursor/Claude): `prompts/deep-research-*.md`

```bash
world-cup-bot research list
world-cup-bot research run group-conviction --group B --json
world-cup-bot research run cross-venue --json
world-cup-bot research run team-lp-risk --team Turkey --json --messages
```

See [prompts/README.md](prompts/README.md) and [prompts/gemini-deep-research/README.md](prompts/gemini-deep-research/README.md). Operational daily gate remains [prompts/advisor.md](prompts/advisor.md).

## Optional LLM advisor (zero cost by default)

The bot runs fully without any LLM. Advisor env vars are **commented out** in `.env.example`.

| Step | Command | API cost |
|------|---------|----------|
| Export context only | `world-cup-bot context --json` | None — pipe into Cursor, Claude, ChatGPT, Ollama |
| In-process review | `world-cup-bot plan --advisor` | Only if `ADVISOR_BASE_URL` is set |
| Hard gate | `world-cup-bot plan --advisor --advisor-gate hard` | Same — skips teams on `skip` / `human_review` |

**Ollama (local, no cloud bill):**

```bash
ollama serve
export ADVISOR_BASE_URL=http://localhost:11434/v1
export ADVISOR_MODEL=llama3.2
world-cup-bot plan --advisor --advisor-gate soft
```

**OpenAI-compatible cloud** (OpenAI, OpenRouter, etc.): set `ADVISOR_BASE_URL` + `ADVISOR_API_KEY`.

If `--advisor` is passed but `ADVISOR_BASE_URL` is unset, the bot **continues without the LLM** and prints a one-line notice. Use `--advisor-strict` to fail instead.

Prompt template: `prompts/advisor.md`. The advisor may only **skip, reduce, or flag** — never raise notional above YAML caps.

## Optional localhost UI (read-only)

No extra dependencies — stdlib HTTP server only. **Not started automatically.**

```bash
world-cup-bot ui
# open http://localhost:8765
```

Tabs: **Ready** (preflight + shadow progress), **Markets**, **Plan preview**, **Calendar**, **PnL**, **Advisor context** (copy JSON). All routes are GET-only; nothing posts orders. Binds **localhost** only by default (`--host` to override).

Config paths resolve against the **repo root** automatically — you can run `world-cup-bot ui` from any directory after `pip install -e .`.

Override port: `world-cup-bot ui --port 8765`. CLI remains the path for `watch`, live fills, and recording.

## 24/7 VPS (systemd, optional)

Run on **your own Linux VPS** so the bot stays up when your laptop is off. Example units live in **`deploy/systemd/`**:

```bash
sudo bash deploy/systemd/install-systemd.sh --install-root /opt/world-cup-bot --profile monitor --enable
```

- **`monitor`** — cross-venue alerts, shadow plan (`--liquidity-gate`), scan, calendar, discover, **pnl-daily**, conviction-staleness, fixture-check, **tournament-ops**, match-shock discover/plan (paper)
- **`trading`** — fill watch + live plan on a **non-US** VPS (order POST geo-blocked from the US); match-shock record/live-plan and cross-venue exec are **manual** enable only
- **`rewards-sync.timer`** — installed with monitor profile but **not** auto-enabled; enable after Phase 2 when L2 creds exist

**Ledger paths on VPS:** systemd units set `WC_LEDGER_PATH` per job (`shadow_ledger.jsonl` for monitor plan/pnl-daily; `ledger.jsonl` for trading watch/live-plan). For `shadow-status`, point **one** canonical file via `.env` (`LEDGER_PATH` = `WC_LEDGER_PATH`) so Phase 1 day counts are not split — see [SHADOW.md](SHADOW.md).

See [deploy/systemd/README.md](deploy/systemd/README.md) for install root, two-VPS split, and SHADOW phase gates. Default path: `/opt/world-cup-bot` — change with `--install-root`.

## Disclaimer

Prediction markets involve loss of capital. LP without cancel discipline around kickoff has burned operators. Read the code before live mode.

## Sources

- [Source: https://github.com/cemini23/world-cup-bot/blob/main/SETUP.md]
- [Source: https://github.com/cemini23/world-cup-bot/blob/main/SHADOW.md]
