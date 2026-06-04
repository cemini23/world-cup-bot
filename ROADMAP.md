# Roadmap

Companion to [README.md](README.md) (overview), [SHADOW.md](SHADOW.md) (go-live gates), and [SETUP.md](SETUP.md) (configuration).

**Logic version:** `wc_advance_lp_v4` · paper arb: `wc_cross_venue_paper_v1` · exec: `wc_cross_venue_exec_v1` · match-shock: `wc_match_shock_v1` · **Tests:** 282 pytest (CI on push)

---

## Public launch — 2026-06-03

- **Repo:** [github.com/cemini23/world-cup-bot](https://github.com/cemini23/world-cup-bot) · **Pages:** [cemini23.github.io/world-cup-bot](https://cemini23.github.io/world-cup-bot/)
- **Distribution:** [Outlier Weekly Issue 3](https://outlierweekly.substack.com/p/i-open-sourced-the-world-cup-lp-bot) (free, live 2026-06-03) — shadow-first LP stack, not financial advice
- **Companion:** [Gambling-wiki](https://github.com/cemini23/Gambling-wiki) for retail WC / PM/Kalshi education
- **Go-live:** Operators complete [SHADOW.md](SHADOW.md); live LP remains opt-in (`DRY_RUN=false`, non-US egress, `WC_LIVE_PLAN_ACK=1`)

---

## Shipped (v1)

| Area | Status |
|------|--------|
| Modules 1–7 | Scanner, conviction, quoter, fill handler, calendar, cross-venue, ledger/PnL |
| Go-live safety | Auto-cancel window, cancel-replace, kill-switch, queue depletion + vol cooldown |
| Liquidity gate | CLOB `GET /book` depth scan; asymmetric bid/ask band floors in `config/operating.yaml` |
| Shadow gate | `shadow-status --min-phase N` with ledger path + step progress (exit 1 on pending/blocked) |
| Operator automation | `conviction-staleness`, `fixture-check`, `conviction-patch --stage`, cross-venue webhooks |
| systemd profiles | Monitor (shadow + alerts) and trading (watch + live plan) — see [deploy/systemd/README.md](deploy/systemd/README.md) |
| **Tournament ops + shock systemd** | `tournament-ops check`; match-shock discover/plan (monitor), record/live-plan (trading, manual) |
| CLOB V2 | Live POST via `py-clob-client-v2`; preflight + CI import guard |
| Security (2026-06) | Env notional ceiling, outbound URL allowlist, `WC_LIVE_PLAN_ACK` live-plan interlock |
| Shadow / ledger (2026-06) | `WC_LEDGER_PATH` in Settings; split-ledger docs; geoblock PASS when CLOB auth OK on EU egress |
| Cross-venue phases A–C | Paper ledger, manual fill bridge, auto dual-leg (off by default) |
| Phase router (1b) | FSM, multi-phase scanner, settlement gate — **flags default OFF** |
| Research CLI | Gemini Deep Research + agent JSON bundles in `prompts/` |
| **Match-shock scaffold (8)** | Discover + Data API export + live WS tape + backtest CLI — see [`docs/MATCH_SHOCK_V1.md`](docs/MATCH_SHOCK_V1.md) |
| **Match-shock complete (8)** | Plan loop, ledger, live POST (gated), bucket grid A–D, tournament-ops + systemd units |

---

## Recommended before live LP

Complete [SHADOW.md](SHADOW.md) Phases 0–3 on your infrastructure:

1. **≥3 days** of `plan --record --liquidity-gate` with `DRY_RUN=true`
2. `watch --record` with L2 credentials
3. `preflight` **PASS** from a **non-US** egress IP
4. Small pilot (`$500–1K` per market) before enabling `world-cup-bot-live-plan.timer`
5. Set `WC_LIVE_PLAN_ACK=1` in `.env` only after Phase 4 operator sign-off

---

## Planned (post-launch)

| Item | Notes |
|------|-------|
| Dependency lockfile | Reproducible `[live]` installs — `requirements-lock.txt` + CI `check_requirements_lock.py` |
| Formal LP promotion gates | DSR + MCPT heuristics in `lp_promotion.py`; shadow-status step `lp_promotion` |
| Wiki enforcement hook | `WC_WIKI_ENFORCEMENT=1` → `wiki_enforcement.py` blocks live POST violations |

---

## Maintainer cadence (optional)

| Item | Schedule | Notes |
|------|----------|-------|
| LP safety deep research | Weekly through tournament | `research run weekly-osint-pipeline` + human review before YAML edits |
| Conviction refresh | After material news | `conviction-staleness --notify`, `fixture-check --notify` |
| Cross-venue pair refresh | As slugs change | `cross-venue-scan --discover-only` → update `config/cross_venue.yaml` |

Current conservative posture: `Canada`, `Japan`, `Scotland`, and `Brazil` remain **`fade_watch`** (alert-only) in `config/conviction.yaml` — K96 review **2026-06-04** confirmed; next review **2026-06-13** or after June friendlies.

---

## OSINT K98 boundary (2026-06-04)

K98 (`@osint-wiki` ingest) adds **BTC/ETH 15m up/down** telemetry on **cemini-prod** (`2026-06-04_k98-pm-latency-fusion-queue-telemetry-cemini-prod.md` — Binance CVD/OBI vs PM lag, pre-open queue rank). **No world-cup-bot code changes:** advance-LP `queue_depletion_usd` is post-fill depth ahead of you, not Polymarket timed-window queue sniping. @Nekt_0 Post 13 (profit concentration / latency in sports) is operator context only — corroborates fast-tape discipline, not a new module.

---

## Out of scope (v1)

- Hosted or managed service
- Guaranteed edge or financial advice
- In-play quoting during live matches
- Kalshi auto-trading without explicit Phase C gates (`WC_CROSS_VENUE_AUTO_EXEC` + `WC_CROSS_VENUE_EXEC_ACK` + non-US egress)

Phase C auto execution requires explicit `WC_CROSS_VENUE_AUTO_EXEC=1`, `WC_CROSS_VENUE_EXEC_ACK=1`, non-US VPS, Kalshi + Polymarket credentials, and SHADOW Phase 4 operator approval. Closed loop: `cross-venue-scan --loop` with auto-exec (systemd `world-cup-bot-cross-venue-exec.service` on trading profile).

---

## Changelog (high level)

| Date | Notes |
|------|-------|
| 2026-05-29 | Go-live safety wave: risk cap, 429 preflight, event log, CI secret scanning |
| 2026-05-30 | Liquidity scanner, phase router PR2, paper cross-venue arb ledger |
| 2026-05-31 | Conviction fade-watch downgrades; phase-status CLI tests |
| 2026-06-01 | CLOB V2 migration; conviction YAML v5 hygiene; weekly research pipeline mode |
| 2026-06-02 | Pre-drop security audit: notional env cap, URL allowlist, live-plan ack gate |
| 2026-06-03 | **Public launch** (Outlier Weekly Issue 3); split-ledger SHADOW docs; `WC_LEDGER_PATH` fix |
| 2026-06-04 | OSINT K98 scope note — prod PM latency brief does not change WC modules |

---

## License

MIT — see [LICENSE](LICENSE).
