# World Cup Bot

[![CI](https://github.com/cemini23/world-cup-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/cemini23/world-cup-bot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Open-source bot for **FIFA World Cup 2026** *advance to knockout stages* markets on [Polymarket](https://polymarket.com).

**Status:** early build — shadow mode first. Public launch tied to [Outlier Weekly](https://outlierweekly.substack.com) Issue 3 (2026-06-03).

## What it does (v1)

| Module | Scope |
|--------|--------|
| **Scanner** | Discovers WC advance markets via Gamma; reads reward params at runtime |
| **Conviction LP** | Resting limits on research-backed mid-tier teams; bilateral mode above ~90¢ |
| **Fill handler** | Limit exit within ~60s; queue-depletion pull; **live fills via user-channel WS** |
| **Optional advisor** | `context --json` or `plan --advisor` — LLM overlay; **off by default** (no API cost) |
| **Optional UI** | `world-cup-bot ui` — read-only localhost dashboard (stdlib, port 8765) |
| **Cross-venue scanner** | Polymarket vs Kalshi advance gaps — **alert-only** in v1 |
| **Ledger** | Daily P&L from fills + rewards |

Prices, spreads, and kickoff times come from **Gamma + CLOB at runtime** — nothing hardcoded.

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
world-cup-bot calendar --team Mexico
world-cup-bot calendar --cancel-window --min-hours 10
world-cup-bot scan              # live Gamma mids + LP eligibility
world-cup-bot scan --conviction # conviction tier + quote gate
world-cup-bot plan              # dry-run quote intents (DRY_RUN=true default)
world-cup-bot plan --record     # append intents to versioned JSONL ledger
world-cup-bot context --json    # decision bundle for external LLM (no API call)
world-cup-bot ui                  # optional read-only dashboard → http://127.0.0.1:8765
world-cup-bot plan --advisor    # optional LLM gate (needs ADVISOR_BASE_URL)
world-cup-bot preflight         # geoblock + Gamma + CLOB auth before live LP
world-cup-bot watch --verbose   # user-channel WS → fill handler (needs L2 API creds)
world-cup-bot pnl               # headline PnL (scope=current logic_version only)
world-cup-bot fill --team Turkey --side YES --order-id ord-1 --price 0.44 --shares 500 --record
world-cup-bot pnl --scope all --by-version  # forensics breakdown
```

Requires a Polymarket account with CLOB API access. Kalshi alerts need separate Kalshi API credentials (optional for LP-only mode).

**Calendar guard (Module 5)** uses vendored [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) fixtures (`data/worldcup2026-fixtures.json`, CC0) — not live prices. See `data/DATA_ATTRIBUTION.md`.

See [SETUP.md](SETUP.md) for environment variables and geoblock notes.

**Shadow → live:** [SHADOW.md](SHADOW.md) phased checklist. **Contributors / AI agents:** [CLAUDE.md](CLAUDE.md).

## Security

- Never commit `.env`, private keys, or wallet seed phrases
- See [SECURITY.md](SECURITY.md) for what stays out of this repo

## Related

- Methodology newsletter: [Outlier Weekly](https://outlierweekly.substack.com)
- Agent toolkit (separate repos): [vet](https://github.com/cemini23/vet) · [wikilint](https://github.com/cemini23/wikilint)

## License

MIT — see [LICENSE](LICENSE).
