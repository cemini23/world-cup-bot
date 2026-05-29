# Shadow mode checklist — before live LP

Run everything with **`DRY_RUN=true`** until Phase 4. Prediction markets can lose capital; LP without cancel discipline around kickoff has burned operators.

## Phase 0 — Install & connectivity

```bash
git clone https://github.com/cemini23/world-cup-bot.git && cd world-cup-bot
cp .env.example .env          # fill keys locally — never commit
pip install -e ".[dev]"
pip install -e ".[live]"        # websockets + py-clob-client (watch / live POST)
world-cup-bot preflight         # geoblock WARN ok in shadow from US
world-cup-bot scan --conviction
world-cup-bot ui                # optional dashboard → http://127.0.0.1:8765
```

**Pass criteria:** Gamma returns markets; preflight has no `FAIL` except geoblock when shadowing from US (WARN is OK).

## Phase 1 — Dry-run quote loop (≥3 sessions)

```bash
world-cup-bot plan              # inspect intents — no POST
world-cup-bot plan --record     # append quote intents to ledger JSONL
world-cup-bot pnl               # confirm quote_intents rows under current logic_version
```

**Pass criteria:**

- [ ] At least **3 separate days** with `plan --record` while `DRY_RUN=true`
- [ ] Conviction rows match your research (Group B: Canada, Bosnia listed; Qatar skipped)
- [ ] No teams inside **cancel window** get quote intents (`calendar --cancel-window`)
- [ ] Review `config/conviction.yaml` caps vs bankroll

## Phase 2 — Fill watch (venue reads, still dry)

Requires L2 API creds in `.env` (derive once via py-clob-client).

```bash
world-cup-bot watch --verbose --record
# Ctrl+C after a session; check stats line (messages, trades, fills)
world-cup-bot pnl --scope all --by-version
```

**Pass criteria:**

- [ ] WS connects; reconcile loop runs (debug log every 30s if no recovered fills)
- [ ] If you have resting orders elsewhere, fills land in ledger with dedup
- [ ] Understand fill → exit intent path (`fill --team …` dry-run for manual test)

## Phase 3 — Non-US egress preflight

Order **POST** is geo-blocked from the US. Run from your trading VPS (e.g. EU/Finland):

```bash
# on egress host with DRY_RUN still true first:
world-cup-bot preflight         # geoblock must PASS
world-cup-bot preflight           # L2 GET /data/orders auth probe passes
```

**Pass criteria:**

- [ ] `geoblock` → PASS (not blocked)
- [ ] `clob_auth` → PASS
- [ ] `py_clob_client` → PASS when preparing for live

## Phase 4 — Live pilot (optional, small size)

Only after Phases 0–3. Start with **$500–1K** single-market pilot per bot spec.

```bash
export DRY_RUN=false            # only on egress host
world-cup-bot preflight         # all PASS
world-cup-bot plan --record     # posts post-only GTC limits
world-cup-bot watch --record    # fills + REST reconcile + exit POST
```

**Pass criteria:**

- [ ] Kill switch fires on cancel-window fills (test with `calendar --team …`)
- [ ] Exit intents post within 60s of fill
- [ ] Daily `pnl` review; bump `logic_version` on material logic changes

## Quick reference

| Check | Command |
|-------|---------|
| Geoblock | `world-cup-bot preflight` |
| Conviction gate | `world-cup-bot scan --conviction` |
| Cancel window | `world-cup-bot calendar --cancel-window` |
| Shadow ledger | `world-cup-bot pnl --scope current` |
| UI readiness | `world-cup-bot ui` → **Ready** tab |

## What shadow mode does *not* prove

- Cross-venue Kalshi gaps (Module 6 not shipped)
- Adverse selection under live match news flow
- `$POLY` airdrop eligibility

See [SETUP.md](SETUP.md) and [CLAUDE.md](CLAUDE.md) for module map and agent rules.
