# Match-shock bucket backtest

Build historical **bucket depth distributions** and optional **paper replay** for `wc_match_shock_v1`.

Full module spec: [`docs/MATCH_SHOCK_V1.md`](../../docs/MATCH_SHOCK_V1.md).

## Quick start (fixture)

```bash
cd /path/to/world-cup-bot
python scripts/shock_backtest/run_bucket_backtest.py \
  tests/fixtures/shock_replay/sample_trades.jsonl \
  --out-distributions data/local/shock_distributions.json \
  --replay
```

## Data acquisition (choose one or combine)

### Path A — Gamma + Polymarket Data API (recommended for pre-WC backtest)

Dome API reached **EOL 2026-04-28** (Polymarket acquisition). Use the public Data API instead.

```bash
world-cup-bot match-shock-discover --out data/local/match_markets.json
world-cup-bot match-shock-export \
  --discovery data/local/match_markets.json \
  --out-dir data/local/shock_tapes \
  --max-trades 5000
python scripts/shock_backtest/run_bucket_backtest.py \
  data/local/shock_tapes/combined.jsonl --replay
```

Standalone script (same export logic):

```bash
python scripts/shock_backtest/data_api_export_shock_tapes.py \
  --discovery data/local/match_markets.json \
  --out-dir data/local/shock_tapes
```

Export uses `takerOnly=false` so maker fills appear in historical tapes. Not all settled markets retain trades — filter discovery to slugs with volume.

### Path B — Live CLOB market channel (WC tournament)

Primary source for **WC 2026** match slugs (not on Gamma until markets list):

```bash
pip install -e ".[live]"
WC_SHOCK_ENABLED=1 world-cup-bot match-shock-record \
  --discovery data/local/match_markets.json \
  --out data/local/shock_tapes/2026-06-11.jsonl
```

Nightly: merge new JSONL into `run_bucket_backtest.py` for distribution updates.

### Path C — pmxt orderbook archive (optional, librarian)

Deep order-book history on `cemini-librarian`. **Deprioritized** when mirror hours contain no football slugs (e.g. 2026-05-25 pilot).

```bash
bash scripts/shock_backtest/sync_pmxt_football_to_librarian.sh --hours 24 --skip-backtest
python scripts/shock_backtest/export_pmxt_shock_tapes.py …
```

Parquet source: `https://r2v2.pmxt.dev/polymarket_orderbook_{YYYY-MM-DDTHH}.parquet`.

OSINT wrapper: `OSINT WORKSPACE/scripts/sync_pmxt_football_to_librarian.sh`.

## Input JSONL schema

One observation per line:

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
| `bids` | no | Top-of-book snapshot (live WS / pmxt only) |

Data API export populates `ts_ms`, `price`, `slug` only — sufficient for shock detection; book-depth classifier uses defaults.

## Outputs

- **stdout** — shock counts, bucket sample sizes
- **`--out-distributions`** — JSON map `bucket_key → [depth_cents, …]` for live lookup
- **`--replay`** — paper win rate + PnL vs `backtest.min_recovery_rate` gate

## Bucket grid A–D

```bash
python scripts/shock_backtest/run_bucket_grid.py \
  tests/fixtures/shock_replay/sample_trades.jsonl \
  --out-dir data/local/shock_backtest
```

Writes `replay_report.json` + `replay_report.md` (runs A–D per OSINT wiki matrix).

## Promotion gates

| Gate | Threshold |
|------|-----------|
| Min samples per bucket | 5 (config `distribution.min_samples_per_bucket`) |
| Paper replay win rate | ≥ `backtest.min_recovery_rate` (default 55%) |
| SHADOW soak | Separate ledger; 3+ days before `WC_MATCH_SHOCK_LIVE=1` |
| Isolation | Never enable on same wallet as advance LP without operator sign-off |

## Related

- `docs/MATCH_SHOCK_V1.md` — module spec + env vars
- `config/shock_match.yaml` — all thresholds
- `world_cup_bot/match_shock.py` — pure functions (detect, classify, ladder)
