# Match-shock v1 (`wc_match_shock_v1`)

**Status:** v2 scaffold — paper-first, **disabled by default** (`config/shock_match.yaml` → `enabled: false`).

In-play match-market shock recovery strategy, orthogonal to advance-to-knockout LP (`wc_advance_lp_v4`). Do **not** wire into `quoter.py` or share cancel-window state with Module 3.

## Unified bot — LP then shock (same process)

One operator stack, two modes — handoff at the **existing cancel window** (`MIN_HOURS_BEFORE_KICKOFF`, default 10h):

| Market kind | Before kickoff | After kickoff |
|-------------|----------------|---------------|
| **Advance** (`advance to knockout`) | **LP mode** (Modules 1–4) | **OFF** — calendar guard cancels; no in-play LP |
| **Match** (90-min / win markets) | **OFF** — no pregame shock | **SHOCK mode** (Module 8) until `max_match_hours` |

Implementation: `world_cup_bot/trading_mode.py` → `resolve_trading_mode()`.

```python
from world_cup_bot.trading_mode import MarketKind, resolve_trading_mode, ModeHandoffConfig

decision = resolve_trading_mode(
    market_kind=MarketKind.MATCH,
    hours_to_kickoff=-0.5,  # 30min into match
    cfg=ModeHandoffConfig(min_hours_before_kickoff=10.0, shock_enabled=True),
)
# decision.mode == TradingMode.SHOCK
```

Env: `WC_SHOCK_ENABLED=1` (planned) + `config/shock_match.yaml` `mode_handoff.shock_enabled`.

**Not two bots** — one calendar, one fixture file, shared kickoff clock; strategies never overlap on the same slug.

## Canonical spec

| Doc | Location |
|-----|----------|
| Architecture | OSINT wiki `wiki/projects/world-cup-bot/Architecture/Architecture - match_shock_v1.md` |
| pmxt backtest design | OSINT wiki `Architecture - match_shock_pmxt_backtest.md` |
| Strategy concept | `@osint-wiki/concepts/polymarket-football-shock-recovery-trading.md` |
| Source post | `@osint-wiki/sources/rohonchain-fifa-wc-shock-recovery-strategy-2026-06-02.md` |

## Repo layout

```
config/shock_match.yaml          # thresholds (detection, classifiers, ladder, backtest filters)
world_cup_bot/match_shock.py     # detect → classify → ladder (pure functions)
world_cup_bot/match_shock_config.py
scripts/shock_backtest/          # bucket distribution builder + paper replay
tests/test_match_shock.py
tests/fixtures/shock_replay/
```

## Logic version

Inline spec (cross-venue pattern):

- `strategy_key`: `pm_wc_match_shock`
- `version_id`: `wc_match_shock_v1`

Separate ledger events: `match_shock_detected`, `match_shock_ladder_planned`, `match_shock_paper_fill`.

## Env gates (planned)

| Variable | Default | Meaning |
|----------|---------|---------|
| `WC_MATCH_SHOCK_LIVE` | unset | `1` required for live POST |
| `WC_MATCH_SHOCK_LEDGER_PATH` | `data/local/match_shock_paper.jsonl` | Paper/live JSONL |

## CLI (planned)

```bash
# Backtest only (today)
python scripts/shock_backtest/run_bucket_backtest.py tests/fixtures/shock_replay/sample_trades.jsonl --replay

# Future
world-cup-bot match-shock-scan --paper
world-cup-bot match-shock-plan --record
```

## Safety

- Advance LP **must** keep DR 09 `hard_halt` in-play.
- Shock module trades the **adverse flow** that picks off stale advance quotes — run on isolated wallet or paper until promoted.
