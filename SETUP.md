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
| `DRY_RUN` | yes | Keep `true` until you have shadow-tested |
| `MIN_HOURS_BEFORE_KICKOFF` | no | Calendar guard cancel threshold (default `10`) |

## Calendar guard

Kickoff times from bundled CC0 fixtures (`data/worldcup2026-fixtures.json`), not Polymarket:

```bash
world-cup-bot calendar --team Turkey
world-cup-bot calendar --cancel-window --min-hours 10
```

Refresh if FIFA reschedules — see `data/DATA_ATTRIBUTION.md`.

## Modes

| Mode | Command (planned) | Posts orders? |
|------|-------------------|---------------|
| Shadow | `DRY_RUN=true` | No — logs intended quotes |
| Live LP | `DRY_RUN=false` | Yes — limit orders only |

## Kalshi (optional)

Cross-venue scanner is **alert-only** in v1. Kalshi credentials optional.

## Disclaimer

Prediction markets involve loss of capital. LP without cancel discipline around kickoff has burned operators. Read the code before live mode.
