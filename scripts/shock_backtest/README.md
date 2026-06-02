# Match-shock bucket backtest (pmxt / JSONL)

Build historical **bucket depth distributions** and optional **paper replay** for `wc_match_shock_v1`.

## Quick start (fixture)

```bash
cd /path/to/world-cup-bot
python scripts/shock_backtest/run_bucket_backtest.py \
  tests/fixtures/shock_replay/sample_trades.jsonl \
  --out-distributions data/local/shock_distributions.json \
  --replay
```

## Input JSONL schema

One trade per line:

```json
{
  "ts_ms": 1710000000000,
  "price": 0.30,
  "slug": "epl-man-united-win-2025-04-01",
  "elapsed_ms": 2100000,
  "goal_diff": 0,
  "bids": [
    {"price": 0.29, "size": 120},
    {"price": 0.28, "size": 80}
  ]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `ts_ms` | yes | Unix epoch milliseconds |
| `price` | yes | YES mid or last trade price (0–1) |
| `slug` | yes | Gamma slug — drives league classifier |
| `elapsed_ms` | no | Match clock; default 0 → `early` bucket |
| `goal_diff` | no | Signed or absolute; default 0 → `level` |
| `bids` | no | Top-of-book snapshot at tick time |

## pmxt data path (production backtest)

Full design: OSINT wiki `@osint-wiki/projects/world-cup-bot/Architecture/Architecture - match_shock_pmxt_backtest.md`.

### Phase 0 — subset on librarian (recommended)

1. **Stage** pmxt mirror subset on `cemini-librarian`:
   `/opt/cemini-bulk/market-dataset/polymarket-orderbook/` (see `@entities/tools/pmxt.md`).
2. **Filter** to football match markets:
   - slug contains `world-cup`, `fifa`, `epl`, `ucl`, `la-liga`, etc.
   - exclude `advance`, `group-winner`, tournament-outright slugs (`config/shock_match.yaml` `markets.blocked_slug_patterns`).
3. **Export** trade tape JSONL per market:
   - Derive `PriceTick` series from pmxt normalized trades or mid snapshots at 1–5s cadence.
   - Join optional match clock from openfootball fixtures or manual CSV for WC replays.
4. **Run** `run_bucket_backtest.py` → `data/local/shock_distributions.json`.
5. **Tune** `config/shock_match.yaml` `backtest.allowed_favoritism` / `allowed_league_tiers` before paper live.

### Phase 1 — live WC capture

Parallel CLOB WS recorder on match slugs during tournament; same JSONL schema. Merge into distributions nightly.

## Outputs

- **stdout** — shock counts, bucket sample sizes
- **`--out-distributions`** — JSON map `bucket_key → [depth_cents, ...]` for live lookup
- **`--replay`** — paper win rate + PnL vs `backtest.min_recovery_rate` gate

## Promotion gates

| Gate | Threshold |
|------|-----------|
| Min samples per bucket | 5 (config `distribution.min_samples_per_bucket`) |
| Paper replay win rate | ≥ `backtest.min_recovery_rate` (default 55%) |
| SHADOW soak | Separate ledger; 3+ days before `WC_MATCH_SHOCK_LIVE=1` |
| Isolation | Never enable on same wallet as advance LP without operator sign-off |

## pmxt sync (librarian)

```bash
# Pilot — 6 hours, ETL only
bash scripts/shock_backtest/sync_pmxt_football_to_librarian.sh --hours 6 --skip-backtest

# Production — 24h + bucket replay
bash scripts/shock_backtest/sync_pmxt_football_to_librarian.sh --hours 24

# Date range
bash scripts/shock_backtest/sync_pmxt_football_to_librarian.sh --from 2026-05-20 --to 2026-05-22
```

Inner worker (on librarian): `run_pmxt_football_sync.sh`. OSINT wrapper: `OSINT WORKSPACE/scripts/sync_pmxt_football_to_librarian.sh`.

## Backtest ETL

```bash
# pmxt export → shock tapes
python scripts/shock_backtest/export_pmxt_shock_tapes.py \
  /path/to/pmxt/export/*.jsonl \
  --out-dir data/local/shock_tapes --per-slug

# bucket distributions + replay
python scripts/shock_backtest/run_bucket_backtest.py \
  data/local/shock_tapes/combined.jsonl --replay
```

## Related

- `docs/MATCH_SHOCK_V1.md` — module spec pointer
- `config/shock_match.yaml` — all thresholds
- `world_cup_bot/match_shock.py` — pure functions (detect, classify, ladder)
