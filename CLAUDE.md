# World Cup Bot — agent schema

Read this at session start. Human docs: [README.md](README.md), [SETUP.md](SETUP.md), [ROADMAP.md](ROADMAP.md), [SECURITY.md](SECURITY.md).

## Purpose

Open-source **conviction LP bot** for Polymarket **FIFA 2026 advance-to-knockout** markets. Shadow-first (`DRY_RUN=true` default). Prices and spreads come from **Gamma + CLOB at runtime** — never hardcode mids or team prices in Python.

**Not in scope for this repo:** hosted service, financial advice, Kalshi auto-trading (alert-only cross-venue).

## Module map

| # | Module | Package file(s) | Status |
|---|--------|-----------------|--------|
| 1 | Scanner | `scanner.py`, `http_client.py` | Live — Gamma `public-search` |
| 1b | Phase router | `phase_router.py`, `market_phases.py`, `settlement_gate.py`, `config/market_phases.yaml` | PR1+PR2 — FSM, multi-phase scanner, settlement gate, SIGUSR1; flags default OFF |
| 2 | Conviction | `conviction.py`, `config/conviction.yaml` | Live — team tiers, quote gate |
| 3 | Quoter | `quoter.py` | Dry-run default; live POST via `clob_live.py` |
| 4 | Fill handler | `fill_handler.py`, `ws_user.py`, `reconcile.py` | WS + 30s REST reconcile; queue depletion + vol cooldown |
| 5 | Calendar guard | `calendar_guard.py`, `data/worldcup2026-fixtures.json` | Live — CC0 fixtures, not Polymarket |
| 6 | Cross-venue | `cross_venue_scanner.py`, `cross_venue_paper.py`, `cross_venue_fills.py`, `cross_venue_exec.py`, `kalshi_auth.py`, `kalshi_orders.py`, `kalshi_rest.py`, `config/cross_venue.yaml` | Alert-only scan; paper ledger; manual fills; **Phase C exec** (gated) |
| 7 | Ledger / PnL | `ledger.py`, `logic_version.py`, `venue_reconcile.py` | JSONL + `logic_version`; venue CSV diff |
| — | Liquidity gate | `liquidity_scanner.py`, `clob_rest.py` | Live — public CLOB `/book`; bid/ask band floors in `operating.yaml` |
| — | Conviction ops | `conviction_staleness.py`, `conviction_patch.py`, `fixture_watch.py` | Staleness alerts, DR patch staging, fixture upstream diff |
| — | Preflight | `preflight.py`, `clob_rest.py`, `clob_signing.py` | Geoblock + auth checks |
| — | Shadow gate | `shadow_checklist.py` | `shadow-status` CLI + UI Ready tab |
| — | Optional advisor | `advisor.py`, `prompts/advisor.md` | Off unless `ADVISOR_BASE_URL` set |
| — | Optional UI | `ui_server.py`, `ui_data.py`, `static/` | Read-only localhost :8765 |

CLI entry: `world_cup_bot/__main__.py` → `world-cup-bot` console script.

## Config vs code (hard rule)

**Thresholds and team lists live in YAML, not Python.**

| File | Holds |
|------|--------|
| `config/conviction.yaml` | Which teams to quote, bilateral/ fade lists, per-team notional caps, `human_review` |
| `config/operating.yaml` | Calendar, bilateral mids, fill-handler seconds/USD/%, **liquidity** bid/ask band depth |
| `config/strategy_logic_versions.yaml` | PnL attribution version (`wc_advance_lp_v4` current) |
| `config/cross_venue.yaml` | PM↔Kalshi pairs, poll interval, `verification_max_age_days` |

CI runs `scripts/check_hardcoded_thresholds.py` (or `.sh` wrapper) — do not add `mid > 0.90`-style literals to `scanner.py`, `quoter.py`, or `fill_handler.py`.

Paths resolve from **repo root** via `paths.py` — CLI works from any cwd after `pip install -e .`.

## Environment

Copy `.env.example` → `.env` (never commit). See SETUP.md for full table.

| Concern | Key vars |
|---------|----------|
| Shadow default | `DRY_RUN=true` |
| Shadow ledger (VPS) | `WC_LEDGER_PATH` or `LEDGER_PATH` — systemd sets `…/shadow_ledger.jsonl` |
| Live POST | `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_FUNDER_ADDRESS`, L2 trio, `pip install -e ".[live]"` |
| Fill watch | L2 creds + `pip install -e ".[live]"` (websockets) |
| Optional LLM | `ADVISOR_BASE_URL` (unset = zero cost) |
| Optional alerts | `WC_ALERT_WEBHOOK_URL` |
| Live plan ack | `WC_LIVE_PLAN_ACK=1` before enabling `live-plan.timer` |
| Notional ceiling | `MAX_NOTIONAL_PER_MARKET_USD` (min with YAML caps) |

Derive L2 creds once: py-clob-client-v2 `create_or_derive_api_creds()` from private key (or Polymarket settings UI).

## Commands (operator)

```bash
pip install -e ".[dev]"          # ruff + pytest
pip install -e ".[live]"          # + websockets, py-clob-client-v2, eth-account

world-cup-bot scan [--conviction] [--liquidity]
world-cup-bot liquidity-scan [--team TEAM]
world-cup-bot plan [--record] [--advisor] [--liquidity-gate]
world-cup-bot preflight [--skip-auth]
world-cup-bot shadow-status [--min-phase N] [--json]
world-cup-bot phase status [--json]
world-cup-bot phase set <state_id|auto>
world-cup-bot phase purge --team NAME
world-cup-bot cross-venue-scan [--discover-only] [--loop] [--record] [--alert-only]
world-cup-bot cross-venue-pnl [--refresh] [--json]
world-cup-bot watch [--verbose] [--record]
world-cup-bot calendar --team NAME | --cancel-window
world-cup-bot cancel --cancel-window | --team NAME | --all-wc
world-cup-bot orders
world-cup-bot pnl [--scope current|legacy|all] [--by-version]
world-cup-bot venue-reconcile compare <polymarket-export.csv> [--logic-version wc_advance_lp_v4]
world-cup-bot rewards sync [--record]
world-cup-bot conviction-staleness [--notify]
world-cup-bot fixture-check [--notify] [--apply]
world-cup-bot conviction-patch FILE [--stage]
world-cup-bot context --json
world-cup-bot ui
```

**Before live LP:** `preflight` from **non-US egress** (order POST geo-blocked from US). Shadow/read-only (scan, ui, liquidity-scan, watch reconcile reads) works on US IP.

## Agent workflow (code changes)

1. Read affected module + YAML config; follow existing patterns (stdlib-first, minimal deps).
2. **No secrets** in git — see SECURITY.md.
3. Before claiming done:
   ```bash
   ruff check world_cup_bot tests
   ruff format world_cup_bot tests
   python scripts/check_hardcoded_thresholds.py
   pytest -q
   ```
4. Bump `config/strategy_logic_versions.yaml` `current.version_id` + `deployed_at` on **material** logic/sizing/execution changes (K75 attribution).
5. Update README / SETUP / ROADMAP / this file if CLI surface or env vars change.
6. Do **not** commit unless the user asks.

## Architecture notes

```
Gamma public-search → AdvanceMarket rows (mid, spread, rewards, kickoff hours)
        ↓
optional CLOB /book → liquidity_scanner (bid/ask band depth vs operating.yaml)
        ↓
conviction.yaml gate → ConvictionResult (human_review blocked unless liquidity auto-clear enabled in operating.yaml)
        ↓
quoter.build_quotes → QuoteIntent[] → submit_quotes (dry or clob_live)
        ↓
watch: user-channel WS TRADE/MATCHED → fill_handler → exit intent → ledger JSONL
        ↓
reconcile loop (30s): GET /data/trades → same fill path (WS silent-fill blind spot)
```

- **Auth layers:** Gamma reads = public + User-Agent. CLOB reads (book/mid) = public. L2 HMAC = `GET /data/orders`, `GET /data/trades`, POST order, rewards. Order EIP-712 signing = private key via **py-clob-client-v2** (`clob_live.py`).
- **Ledger:** `data/local/ledger.jsonl` default; prod shadow uses `shadow_ledger.jsonl` via `WC_LEDGER_PATH`. PnL scoped by `logic_version`.
- **Advisor:** may only skip, reduce notional, or flag — never raise above YAML caps (`prompts/advisor.md`).

## Operational lessons (read before debugging)

1. **Gamma HTTP 403 from US is usually Cloudflare**, not geoblock — bare Python `urllib` lacks User-Agent. Fixed in `http_client.py`; always use `urlopen_get` for Gamma and CLOB `/book`.
2. **US geoblock blocks order POST**, not Gamma public-search reads. `preflight` geoblock is WARN in shadow, FAIL when `DRY_RUN=false`.
3. **WebSocket alone misses silent fills** — `watch` must run REST reconcile (`reconcile.py` every 30s). Pair both before live capital.
4. **Calendar ≠ prices** — kickoffs from vendored fixtures; `fixture-check` diffs upstream openfootball JSON.
5. **Never infer fills from timeouts** — only venue-confirmed WS or REST trade rows (`FillEvent` docstring).
6. **Proxy wallets** — set `POLYMARKET_FUNDER_ADDRESS` + `POLYMARKET_SIGNATURE_TYPE=2`; reconcile uses funder as `maker_address` on `/data/trades`.
7. **PnL daily ≠ rewards daily** — systemd splits units; rewards sync fails without L2 creds.

## Open backlog (do not claim done)

- ~~Formal shadow gate in GitHub Actions~~ — **Done:** `tests/test_shadow_fixture_gate.py` + TruffleHog/vet in CI
- Dependency lockfile for reproducible `[live]` installs (post-launch)

## Related

- Newsletter: [Outlier Weekly Issue 3](https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot) (live 2026-06-03) · [home](https://outlierweekly.substack.com)
- **Gambling-wiki** (public): retail WC 2026 + PM/Kalshi wagering — [prediction markets crossover](https://github.com/cemini23/Gambling-wiki/blob/main/wiki/concepts/prediction-markets-crossover.md). This repo stays automation/LP; gambling-wiki stays bankroll/CLV/books.
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
