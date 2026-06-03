# Match-shock v1 (`wc_match_shock_v1`)

**Status:** Module 8 scaffold — **paper-first**, disabled by default (`config/shock_match.yaml` → `enabled: false`).

In-play match-market shock recovery (RoH-style), orthogonal to advance-to-knockout LP (`wc_advance_lp_v4`). Do **not** wire into `quoter.py` or share cancel-window state with Module 3.

## Unified bot — LP then shock (same process)

One operator stack, two modes — handoff at the **existing cancel window** (`MIN_HOURS_BEFORE_KICKOFF`, default 10h):

| Market kind | Before kickoff | After kickoff |
|-------------|----------------|---------------|
| **Advance** (`advance to knockout`) | **LP mode** (Modules 1–4) | **OFF** — calendar guard cancels; no in-play LP |
| **Match** (90-min / beat / win markets) | **OFF** — no pregame shock | **SHOCK mode** (Module 8) until `max_match_hours` |

Implementation: `world_cup_bot/trading_mode.py` → `resolve_trading_mode()`.

Env: `WC_SHOCK_ENABLED=1` + `config/shock_match.yaml` → `mode_handoff.shock_enabled`.

**Not two bots** — one calendar, one fixture file, shared kickoff clock; strategies never overlap on the same slug.

## Data paths (historical + live)

Two complementary tracks feed the same JSONL tape schema for `run_bucket_backtest.py`:

| Track | When | Command | Notes |
|-------|------|---------|-------|
| **A — Gamma + Data API** | Pre-tournament backtest | `match-shock-discover` → `match-shock-export` | Polymarket public `data-api.polymarket.com/trades`; **Dome API EOL 2026-04-28** |
| **B — Live CLOB WS** | During matches (WC Jun 11+) | `match-shock-record` | Public `/ws/market` channel; primary source for WC 2026 slugs |
| **C — pmxt archive** | Optional deep OB history | `sync_pmxt_football_to_librarian.sh` | Librarian-only; deprioritized until football-dense hours identified |

### Operator workflow

```bash
# 1. Discover match / beat markets (Gamma public-search)
world-cup-bot match-shock-discover --out data/local/match_markets.json

# 2. Export trade history → shock JSONL (Data API, takerOnly=false)
world-cup-bot match-shock-export \
  --discovery data/local/match_markets.json \
  --out-dir data/local/shock_tapes \
  --max-trades 5000

# 3. Bucket distributions + paper replay
python scripts/shock_backtest/run_bucket_backtest.py \
  data/local/shock_tapes/combined.jsonl \
  --out-distributions data/local/shock_distributions.json \
  --replay

# 4. Live tape during tournament (requires pip install -e ".[live]")
WC_SHOCK_ENABLED=1 world-cup-bot match-shock-record \
  --discovery data/local/match_markets.json
```

**Pilot note (2026-06):** Gamma discovery returns ~200+ historical match slugs (WC 2022, UCL, EPL). **WC 2026 match markets are not listed yet** — live capture from kickoff is the canonical path for tournament data.

## Canonical spec

| Doc | Location |
|-----|----------|
| Architecture | OSINT wiki `Architecture - match_shock_v1.md` |
| Backtest / ETL design | OSINT wiki `Architecture - match_shock_pmxt_backtest.md` |
| Strategy concept | `@osint-wiki/concepts/polymarket-football-shock-recovery-trading.md` |
| Source post | `@osint-wiki/sources/rohonchain-fifa-wc-shock-recovery-strategy-2026-06-02.md` |
| Backtest README | `scripts/shock_backtest/README.md` |

## Repo layout

```
config/shock_match.yaml              # thresholds (detection, classifiers, ladder, backtest filters)
world_cup_bot/
  match_shock.py                     # detect → classify → ladder (pure functions)
  match_shock_config.py
  match_market_discovery.py          # Gamma public-search for beat/match slugs
  data_api_client.py                 # Polymarket Data API /trades pagination
  shock_tape_export.py               # Data API → JSONL
  shock_tape.py                      # shared JSONL parse + scan + replay
  match_shock_ledger.py              # dedicated JSONL events
  match_shock_plan.py                # in-play paper scanner loop
  match_shock_post.py                # gated live ladder POST
  ws_market.py                       # CLOB market-channel parser
  match_shock_record.py              # live WS → JSONL writer
  trading_mode.py                    # LP vs SHOCK mode handoff
  tournament_ops.py                  # bundled fixture/staleness/discover check
scripts/shock_backtest/
  run_bucket_backtest.py             # bucket distributions + replay
  run_bucket_grid.py                 # grid runs A–D + replay_report
  data_api_export_shock_tapes.py     # standalone export script (same logic as CLI)
  export_pmxt_shock_tapes.py         # pmxt JSONL path
  pmxt_parquet_to_jsonl.py           # pmxt v2 parquet → JSONL
  sync_pmxt_football_to_librarian.sh # librarian mirror (optional)
tests/test_match_shock.py
tests/test_match_market_discovery.py
tests/test_ws_market.py
tests/test_shock_tape_export.py
tests/fixtures/shock_replay/
```

## Logic version

Inline spec (cross-venue pattern):

- `strategy_key`: `pm_wc_match_shock`
- `version_id`: `wc_match_shock_v1`

Separate ledger events: `match_shock_detected`, `match_shock_ladder_planned`, `match_shock_paper_fill`.

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `WC_SHOCK_ENABLED` | unset | `1` enables match-shock record path |
| `WC_MATCH_SHOCK_LIVE` | unset | `1` required for live limit POST |
| `WC_MATCH_SHOCK_LIVE_ACK` | unset | `1` required before live plan timer (mirror `WC_LIVE_PLAN_ACK`) |
| `WC_MATCH_SHOCK_TAPE_DIR` | `data/local/shock_tapes` | Default directory for export + live tapes |
| `WC_MATCH_SHOCK_LEDGER_PATH` | `data/local/match_shock_paper.jsonl` | Paper/live JSONL |
| `POLYMARKET_WS_MARKET_URL` | `wss://…/ws/market` | CLOB market channel |
| `POLYMARKET_DATA_API_URL` | `https://data-api.polymarket.com` | Trade history export |

## CLI reference

| Command | Purpose |
|---------|---------|
| `match-shock-discover [--out PATH] [--json]` | Gamma discovery → condition IDs + token IDs |
| `match-shock-export [--discovery PATH] [--out-dir DIR] [--max-trades N]` | Data API → shock JSONL |
| `match-shock-record [--discovery PATH] [--slug FILTER] [--dry-run] [--force]` | Live WS tape (needs `WC_SHOCK_ENABLED=1` or `--force`) |
| `match-shock-plan [--discover-json PATH] [--tape PATH] [--live] [--loop]` | In-play paper scanner; optional live POST when gated |
| `match-shock-post --slug S --token-id T --pre-price P [--submit]` | Ladder POST (default dry-run intents) |
| `tournament-ops check [--strict] [--json]` | Fixture drift + conviction staleness + cross-venue discover |

## Deferred (v1.1)

- Match clock + score feed join (`elapsed_ms`, `goal_diff` precision beyond tape defaults)

## Safety

- Advance LP **must** keep DR 09 `hard_halt` in-play.
- Shock module trades the **adverse flow** that picks off stale advance quotes — run on isolated wallet or paper until promoted.
- Historical Data API tapes may lack order-book depth (`bids[]`) — classifier dim 3 defaults to conservative buckets.
