# World Cup Bot — agent schema

Read this at session start. Human docs: [README.md](README.md), [SETUP.md](SETUP.md), [SECURITY.md](SECURITY.md).

## Purpose

Open-source **conviction LP bot** for Polymarket **FIFA 2026 advance-to-knockout** markets. Shadow-first (`DRY_RUN=true` default). Prices and spreads come from **Gamma + CLOB at runtime** — never hardcode mids or team prices in Python.

**Not in scope for this repo:** hosted service, financial advice, Kalshi auto-trading (alert-only cross-venue is roadmapped).

## Module map

| # | Module | Package file(s) | Status |
|---|--------|-----------------|--------|
| 1 | Scanner | `scanner.py`, `http_client.py` | Live — Gamma `public-search` |
| 2 | Conviction | `conviction.py`, `config/conviction.yaml` | Live — team tiers, quote gate |
| 3 | Quoter | `quoter.py` | Dry-run default; live POST via `clob_live.py` |
| 4 | Fill handler | `fill_handler.py`, `ws_user.py`, `reconcile.py` | WS + 30s REST reconcile |
| 5 | Calendar guard | `calendar_guard.py`, `data/worldcup2026-fixtures.json` | Live — CC0 fixtures, not Polymarket |
| 6 | Cross-venue | `cross_venue_scanner.py`, `kalshi_rest.py`, `pm_discovery.py`, `config/cross_venue.yaml` | Live — alert-only PM vs Kalshi |
| 7 | Ledger / PnL | `ledger.py`, `logic_version.py` | Live — JSONL + version filter |
| — | Preflight | `preflight.py`, `clob_rest.py`, `clob_signing.py` | Geoblock + auth checks |
| — | Optional advisor | `advisor.py`, `prompts/advisor.md` | Off unless `ADVISOR_BASE_URL` set |
| — | Optional UI | `ui_server.py`, `ui_data.py`, `static/` | Read-only localhost :8765 |

CLI entry: `world_cup_bot/__main__.py` → `world-cup-bot` console script.

## Config vs code (hard rule)

**Thresholds and team lists live in YAML, not Python.**

| File | Holds |
|------|--------|
| `config/conviction.yaml` | Which teams to quote, bilateral/ fade lists, per-team notional caps |
| `config/operating.yaml` | Calendar, bilateral mids, fill-handler seconds/USD/% |
| `config/strategy_logic_versions.yaml` | PnL attribution version (`wc_advance_lp_v3` current) |

CI runs `scripts/check_hardcoded_thresholds.sh` — do not add `mid > 0.90`-style literals to `scanner.py`, `quoter.py`, or `fill_handler.py`.

Paths resolve from **repo root** via `paths.py` — CLI works from any cwd after `pip install -e .`.

## Environment

Copy `.env.example` → `.env` (never commit). See SETUP.md for full table.

| Concern | Key vars |
|---------|----------|
| Shadow default | `DRY_RUN=true` |
| Live POST | `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER_ADDRESS`, L2 trio, `pip install -e ".[live]"` |
| Fill watch | L2 creds + `pip install -e ".[live]"` (websockets) |
| Optional LLM | `ADVISOR_BASE_URL` (unset = zero cost) |

Derive L2 creds once: py-clob-client `create_or_derive_api_creds()` from private key.

## Commands (operator)

```bash
pip install -e ".[dev]"          # ruff + pytest
pip install -e ".[live]"          # + websockets, py-clob-client, eth-account

world-cup-bot scan [--conviction]
world-cup-bot plan [--record] [--advisor]
world-cup-bot preflight [--skip-auth]
world-cup-bot watch [--verbose] [--record]
world-cup-bot calendar --team NAME | --cancel-window
world-cup-bot cancel --cancel-window | --team NAME | --all-wc
world-cup-bot orders
world-cup-bot pnl [--scope current|legacy|all] [--by-version]
world-cup-bot context --json
world-cup-bot cross-venue-scan [--discover-only] [--loop] [--alert-only]
world-cup-bot ui
```

**Before live LP:** `preflight` from **non-US egress** (order POST geo-blocked from US). Shadow/read-only (scan, ui, watch reconcile reads) works on US IP.

## Agent workflow (code changes)

1. Read affected module + YAML config; follow existing patterns (stdlib-first, minimal deps).
2. **No secrets** in git — see SECURITY.md.
3. Before claiming done:
   ```bash
   ruff check world_cup_bot tests
   ruff format world_cup_bot tests
   bash scripts/check_hardcoded_thresholds.sh
   pytest -q
   ```
4. Bump `config/strategy_logic_versions.yaml` `current.version_id` + `deployed_at` on **material** logic/sizing/execution changes (K75 attribution).
5. Update README / SETUP / this file if CLI surface or env vars change.
6. Do **not** commit unless the user asks.

## Architecture notes

```
Gamma public-search → AdvanceMarket rows (mid, spread, rewards, kickoff hours)
        ↓
conviction.yaml gate → ConvictionResult
        ↓
quoter.build_quotes → QuoteIntent[] → submit_quotes (dry or clob_live)
        ↓
watch: user-channel WS TRADE/MATCHED → fill_handler → exit intent → ledger JSONL
        ↓
reconcile loop (30s): GET /data/trades → same fill path (WS silent-fill blind spot)
```

- **Auth layers:** Gamma reads = public + User-Agent. CLOB reads (book/mid) = public. L2 HMAC = `GET /data/orders`, `GET /data/trades`, POST order. Order EIP-712 signing = private key via py-clob-client.
- **Ledger:** `data/local/ledger.jsonl` (gitignored path default). PnL scoped by `logic_version`.
- **Advisor:** may only skip, reduce notional, or flag — never raise above YAML caps (`prompts/advisor.md`).

## Operational lessons (read before debugging)

These are the recurring production gotchas — no separate LESSONS.md needed yet.

1. **Gamma HTTP 403 from US is usually Cloudflare**, not geoblock — bare Python `urllib` lacks User-Agent. Fixed in `http_client.py`; always use `urlopen_get` for Gamma.
2. **US geoblock blocks order POST**, not Gamma public-search reads. `preflight` geoblock is WARN in shadow, FAIL when `DRY_RUN=false`.
3. **WebSocket alone misses silent fills** — `watch` must run REST reconcile (`reconcile.py` every 30s). Pair both before live capital.
4. **Calendar ≠ prices** — kickoffs from vendored fixtures; refresh `data/worldcup2026-fixtures.json` if FIFA reschedules.
5. **Never infer fills from timeouts** — only venue-confirmed WS or REST trade rows (`FillEvent` docstring).
6. **Proxy wallets** — set `POLYMARKET_FUNDER_ADDRESS` + `POLYMARKET_SIGNATURE_TYPE=2`; reconcile uses funder as `maker_address` on `/data/trades`.

## Open backlog (do not claim done)

- Formal shadow/MCPT gate checklist in CI (operator checklist: `SHADOW.md` + UI **Ready** tab)
- Rewards accrual into ledger (`rewards_usd` field unused)

## Related

- Newsletter: [Outlier Weekly](https://outlierweekly.substack.com) — Issue 3 launch ~2026-06-03
- Optional VPS: [deploy/systemd/README.md](deploy/systemd/README.md)
- Sibling OSS: [vet](https://github.com/cemini23/vet), [wikilint](https://github.com/cemini23/wikilint)

## Skills / extra agent files

**No in-repo Cursor skills required** — this repo is one Python package + YAML + tests.

| Lane | Path |
|------|------|
| Daily LP gate | `prompts/advisor.md` + `context --json` |
| Gemini Deep Research | `prompts/gemini-deep-research/` + `research gemini <mode>` |
| Agent JSON research | `prompts/deep-research-*.md` + `research run <mode> --json` |

See `prompts/README.md` for mode catalog.
