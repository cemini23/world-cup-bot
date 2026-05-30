# Setup

## Prerequisites

- Python 3.11+
- Polymarket account with CLOB API access (for live LP only)
- US geoblock: check `GET https://polymarket.com/api/geoblock` from your egress IP before live orders

**Gamma reads vs trading:** `gamma-api.polymarket.com` public-search works from a US IP when the client sends a normal `User-Agent` (bare Python `urllib` gets HTTP 403 from Cloudflare). **Order POST** is geo-blocked from the US — use non-US egress (see repo geoblock notes) for live quotes.

## Environment

Copy `.env.example` → `.env` and fill values locally.

| Variable | Required | Notes |
|----------|----------|-------|
| `POLYMARKET_PRIVATE_KEY` | LP mode | CLOB signing key |
| `POLYMARKET_FUNDER_ADDRESS` | LP mode | Proxy/funder address |
| `POLYMARKET_API_KEY` | `watch` | L2 API key (UUID) — not Builder keys |
| `POLYMARKET_API_SECRET` | `watch` | L2 API secret |
| `POLYMARKET_API_PASSPHRASE` | `watch` | L2 API passphrase |
| `DRY_RUN` | yes | Keep `true` until you have shadow-tested |
| `MIN_HOURS_BEFORE_KICKOFF` | no | Calendar guard cancel threshold (default `10`) |

Derive L2 creds once from your private key (py-clob-client `create_or_derive_api_creds()`), then store the three values above in `.env`.

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

Checks: geoblock, Gamma public-search, CLOB `/time`, L2 creds, optional `GET /data/orders` auth probe, `py-clob-client` when `DRY_RUN=false`.

## Live POST (DRY_RUN=false)

```bash
pip install -e ".[live]"   # py-clob-client + websockets + eth-account
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
```

Refresh if FIFA reschedules — see `data/DATA_ATTRIBUTION.md`.

## Modes

| Mode | Command | Posts orders? |
|------|---------|---------------|
| Shadow | `DRY_RUN=true` | No — logs intended quotes |
| Fill watch | `world-cup-bot watch` | No — ingests venue fills over WS |
| Live LP | `DRY_RUN=false` | Yes — limit orders only |

See [SHADOW.md](SHADOW.md) for the phased go-live checklist (≥3 dry-run days, watch, egress preflight).

## Kalshi (optional)

Module 6 cross-venue scanner is **alert-only** — read-only Gamma + Kalshi public APIs. No Kalshi credentials required for scanning.

```bash
world-cup-bot cross-venue-scan              # scan config pairs once
world-cup-bot cross-venue-scan --discover-only   # new PM↔Kalshi pairs for YAML
world-cup-bot cross-venue-scan --loop       # poll every poll_interval_sec (YAML)
world-cup-bot cross-venue-scan --alert-only # stdout alerts + slug-change warnings only
```

When Polymarket slugs change or new WC markets appear, run `--discover-only`, review `rules_hash`, paste rows into `config/cross_venue.yaml`.

Kalshi trading credentials remain optional (`.env` — not used by scanner v1).

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
# open http://127.0.0.1:8765
```

Tabs: **Ready** (preflight + shadow progress), **Markets**, **Plan preview**, **Calendar**, **PnL**, **Advisor context** (copy JSON). All routes are GET-only; nothing posts orders. Binds `127.0.0.1` by default.

Config paths resolve against the **repo root** automatically — you can run `world-cup-bot ui` from any directory after `pip install -e .`.

Override port: `world-cup-bot ui --port 8765`. CLI remains the path for `watch`, live fills, and recording.

## 24/7 VPS (systemd, optional)

Run on **your own Linux VPS** so the bot stays up when your laptop is off. Example units live in **`deploy/systemd/`**:

```bash
sudo bash deploy/systemd/install-systemd.sh --profile monitor --enable
```

- **`monitor`** — cross-venue alerts, shadow plan, scan, calendar (works from US IP; read-only)
- **`trading`** — fill watch + live plan on a **non-US** VPS (order POST is geo-blocked from the US)

See [deploy/systemd/README.md](deploy/systemd/README.md) for install root, two-VPS split, and SHADOW phase gates. Default path: `/opt/world-cup-bot` — change with `--install-root`.

## Disclaimer

Prediction markets involve loss of capital. LP without cancel discipline around kickoff has burned operators. Read the code before live mode.
