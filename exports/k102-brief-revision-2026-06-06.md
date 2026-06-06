# K102 brief revision — WC streak sizing & portfolio gates

**Supersedes:** `/opt/cemini/briefs/2026-06-06_k102-wc-bot-streak-sizing-protection-cemini-prod.md` (implementation corrections)

**Status:** Shipped — **on by default** (2026-06-06). Portfolio gates defer in `DRY_RUN`; live bankroll syncs from PM wallet.

---

## Corrections vs original brief

| Original brief | Corrected spec |
|----------------|----------------|
| Ledger `event=fill` | `event=order_fill` (signed `pnl_usd`; scoped by `logic_version`) |
| `quote_cap_usd` in YAML | Per-team caps stay in `conviction.yaml` → `max_notional_usd`; streak only applies a **multiplier** |
| `min_quote_pct` / `max_quote_pct` | `min_size_multiplier` / `max_size_multiplier` in `config/risk_gates.yaml` |
| Replace daily adverse cap | **Coexists** with `operating.yaml` → `risk.max_daily_adverse_fill_usd` (absolute USD). Plan runs both checks. |
| CeminiSuite CongestionRiskController | **Polymarket-bot v3.1** exponential math (Python-native in `streak_sizing.py`) |
| Single config file merge | Dedicated `config/risk_gates.yaml`; breach rows tagged `logic_version: wc_risk_gates_v1` |

---

## Config (`config/risk_gates.yaml`)

Both layers default **`enabled: true`**. Portfolio gates defer in shadow until live wallet is available.

### Dynamic sizing (streak multiplier)

- Loss: after `loss_streak_threshold` consecutive losing fills, multiply by `(1 - loss_reduction_pct)` per extra loss.
- Win: after `win_streak_threshold` consecutive winning fills, add `win_increase_pct` per step, capped by `win_streak_cap`, then clamp to `[min_size_multiplier, max_size_multiplier]`.
- Applied in `plan` as: `advisor_team_mult × streak_mult` → `build_quotes(..., notional_multiplier=..., max_notional_multiplier=max_streak_mult)`.

### Portfolio gates (% of bankroll)

Live bankroll syncs from **PM wallet** (free USDC + open BUY lock) when `WC_BANKROLL_FROM_WALLET=1` (default). Optional static override: `WC_BANKROLL_USD`.

| Gate | Default threshold | Pause |
|------|-------------------|-------|
| `daily_loss` | 5% realized loss today | 60 min |
| `monthly_loss` | 15% realized loss this month | 30 days |
| `peak_drawdown` | 25% from peak equity | 7 days |
| `total_loss` | 40% cumulative loss vs bankroll | **Permanent halt** (`risk_permanent_halt`) |

Breaches append `risk_gate_breach` or `risk_permanent_halt` to the ledger for audit + pause enforcement.

---

## CLI / observability

```bash
world-cup-bot risk-status          # human summary
world-cup-bot risk-status --json   # streak + portfolio payload
world-cup-bot shadow-status --json # includes risk_gates block
```

Plan aborts when portfolio gates block (after existing daily adverse-fill cap).

---

## Rollout

1. Clone + `bash scripts/shadow_setup.sh` — gates on by default; portfolio % deferred in DRY_RUN.
2. Go live with L2 creds + `WC_BANKROLL_FROM_WALLET=1` (default in `.env.example`).
3. Monitor `world-cup-bot risk-status` each session.
4. Permanent halt requires manual ledger review + operator ack before clearing (no auto-resume).

---

## Tests

- `tests/test_streak_sizing.py` — multiplier math + ledger streak extraction (≥8 cases).
- `tests/test_portfolio_gates.py` — bankroll required, daily breach pause, permanent halt, active pause.

Run: `pytest tests/test_streak_sizing.py tests/test_portfolio_gates.py`

---

## Files touched

| File | Role |
|------|------|
| `config/risk_gates.yaml` | Thresholds, **on by default** |
| `world_cup_bot/streak_sizing.py` | Streak math |
| `world_cup_bot/portfolio_gates.py` | % gates + ledger breaches |
| `world_cup_bot/risk_gates_config.py` | YAML loader |
| `world_cup_bot/risk_status.py` | Status payload |
| `world_cup_bot/quoter.py` | `max_notional_multiplier` for win-streak upsizing |
| `world_cup_bot/__main__.py` | Plan integration + `risk-status` CLI |
| `world_cup_bot/shadow_checklist.py` | Ready tab `risk_gates` block |

**No bump** to `wc_advance_lp_v*` — attribution unchanged while gates are OFF.
