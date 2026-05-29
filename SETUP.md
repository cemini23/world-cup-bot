# Setup

## Prerequisites

- Python 3.11+
- Polymarket account with CLOB API access
- US geoblock: check `GET https://polymarket.com/api/geoblock` from your egress IP before live orders

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

Pair with periodic REST `/orders` reconciliation before live capital (stub loop runs every 30s; full HMAC pass is a follow-up). WS alone can miss silent fills per Cemini wiki.

## Calendar guard

Kickoff times from bundled CC0 fixtures (`data/worldcup2026-fixtures.json`), not Polymarket:

```bash
world-cup-bot calendar --team Turkey
world-cup-bot calendar --cancel-window --min-hours 10
```

Refresh if FIFA reschedules — see `data/DATA_ATTRIBUTION.md`.

## Modes

| Mode | Command | Posts orders? |
|------|---------|---------------|
| Shadow | `DRY_RUN=true` | No — logs intended quotes |
| Fill watch | `world-cup-bot watch` | No — ingests venue fills over WS |
| Live LP | `DRY_RUN=false` | Yes — limit orders only |

## Kalshi (optional)

Cross-venue scanner is **alert-only** in v1. Kalshi credentials optional.

## Disclaimer

Prediction markets involve loss of capital. LP without cancel discipline around kickoff has burned operators. Read the code before live mode.
