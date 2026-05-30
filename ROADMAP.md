# Roadmap

Companion to [README.md](README.md) (operator surface), [SHADOW.md](SHADOW.md) (go-live gates), [CLAUDE.md](CLAUDE.md) (agent schema).

**Logic version:** `wc_advance_lp_v4` · paper arb: `wc_cross_venue_paper_v1` · **Tests:** 159 pytest (CI on push)

---

## Shipped (v1 + automation wave — main @ `17708e1`)

| Area | Status |
|------|--------|
| Modules 1–7 | Scanner, conviction, quoter, fill handler, calendar, cross-venue, ledger/PnL |
| Go-live safety | Auto-cancel window, cancel-replace, kill-switch, queue depletion + vol cooldown |
| **Liquidity gate** | CLOB `GET /book` depth scan; asymmetric bid ($50) / ask ($15) band floors in `config/operating.yaml`; optional auto-clear of `human_review` when depth passes |
| **Shadow gate** | `shadow-status --min-phase N` prints **ledger path** + step progress (exit 1 on pending/blocked) |
| **Operator automation** | `conviction-staleness`, `fixture-check`, `conviction-patch --stage`, cross-venue webhooks + `last_verified` staleness |
| **systemd monitor** | cross-venue (`--record` paper arb), shadow-plan (`--liquidity-gate`), scan, calendar, discover, conviction-staleness, fixture-check |
| **systemd split cron** | `pnl-daily` = PnL only (shadow ledger, no L2); `rewards-sync` = separate unit (opt-in after Phase 2) |
| Rewards CLI | `rewards sync --record` → CLOB `/rewards/user` |
| Research | Gemini DR + agent JSON bundles in `prompts/` |

---

## Open (operator / maintainer)

| Item | Target | Notes |
|------|--------|-------|
| **SHADOW Phase 1 soak** | Before Issue 3 (2026-06-03) | ≥3 days `plan --record --liquidity-gate` on prod shadow ledger; `shadow-status --min-phase 1` PASS |
| **Prod unit refresh** | After `git pull` | Re-run `install-systemd.sh --profile monitor` on monitor VPS; verify `WC_LEDGER_PATH` → shadow ledger |
| **Rewards timer** | Phase 2+ | `systemctl enable --now world-cup-bot-rewards-sync.timer` only after L2 creds on trading/monitor host |
| **LP safety DR re-run** | **2026-06-06** | Weekly cadence — see OSINT wiki `wc-lp-safety-cadence`; update `conviction.yaml` if verdicts change |
| **Phase router (Module 1b)** | **2026-05-30** | PR1+PR2 on `main` — FSM, multi-phase scanner, settlement gate, SIGUSR1 reload; flags default OFF |
| **Cross-venue pair refresh** | Ongoing | `discover` timer + manual `cross-venue-scan --discover-only` when PM advance slugs firm |
| **Paper arb ledger (Phase A)** | **2026-05-30** | `cross-venue-scan --record` + `cross-venue-pnl --refresh` — no execution |
| **Prod cross-venue `--record`** | After pull | Patch cross-venue unit: add `--record`, set `WC_CROSS_VENUE_LEDGER_PATH`; see prod brief |
| **Cross-venue Phase B** | **2026-05-30** | `cross-venue-fill record|import-csv|reconcile` — manual dual-leg bridge |
| **Phase router PR3** | **2026-05-30** | Replay JSONL fixtures, FIFA match gate, per-phase `bilateral_threshold` |
| **Cross-venue Phase C** | Backlog | Kalshi order module + dual-leg coordinator, orphan leg handling, capital caps |
| **Trading VPS profile** | Phase 2–4 | Non-US host: `watch`, then live plan after SHADOW Phases 3–4 |
| **CeminiSuite import** | Post shadow gate | `briefs/2026-05-29_world-cup-bot-cemini-import.md` (OSINT) — skill_audit before scp |

### Steal-from audit (2026-05-29) — shipped

| Fix | Artifact |
|-----|----------|
| Blind-spot checklist + halt playbook | `SHADOW.md` |
| Daily adverse-fill cap | `config/operating.yaml` → `risk`, `world_cup_bot/risk.py` |
| `plan_abort` event logging | `world_cup_bot/event_log.py` |
| CLOB 429 burst preflight | `preflight.py` → `clob_rate_limit` |
| Shadow fixture CI gate | `tests/test_shadow_fixture_gate.py` |
| TruffleHog + vet CI | `.github/workflows/ci.yml` |
| Module 6 doc drift | `prompts/` |

See OSINT `briefs/2026-05-29_world-cup-bot-cemini-steal-from-audit.md`.

---

## Out of scope (v1)

- Kalshi auto-trading (alert-only cross-venue; paper ledger records intent only)
- Hosted/managed service
- Guaranteed edge / financial advice

---

## Cross-venue arb phases

| Phase | Status | Scope |
|-------|--------|-------|
| **A — Paper ledger** | **Shipped** | On `ALERT`, append `cross_venue_arb_intent_paper` to JSONL; `cross-venue-pnl --refresh` MTM vs live gap |
| **B — Manual bridge** | **Shipped** | `cross-venue-fill record`, CSV import, reconcile vs paper intents |
| **C — Auto dual-leg** | Planned | Kalshi order placement + PM hedge coordinator; orphan handling; pilot notional caps |

Phase A does **not** change shadow LP notional or SHADOW gates. Enable `--record` on monitor host only.

---

## Changelog (high level)

| Date | Commit | Notes |
|------|--------|-------|
| 2026-05-29 | (steal-from) | K85 Cemini audit: risk cap, 429 preflight, event log, CI TruffleHog/vet, shadow fixture gate |
| 2026-05-30 | `17708e1` | Liquidity scanner, asymmetric ask threshold, shadow ledger path in gate, split pnl/rewards systemd, fill-handler automation |
| 2026-05-30 | `c143072` | `conviction.yaml` v4 LP safety gates (Spain, Brazil, Morocco) |
| 2026-05-30 | `922a171` | Phase router PR2: multi-phase scanner, settlement gate, SIGUSR1 reload |
| 2026-05-30 | `9f17058` | Paper cross-venue arb ledger (Phase A); systemd cross-venue `--record` |
| 2026-05-30 | (Phase B) | Manual fill bridge: `cross-venue-fill record|import-csv|reconcile` |
| 2026-05-30 | (PR3) | Phase router replay JSONL, FIFA match gate, bilateral_threshold in plan |

## Sources

- [Source: https://github.com/cemini23/world-cup-bot]
- [Source: OSINT briefs/2026-05-29_world-cup-bot-cemini-steal-from-audit.md]
