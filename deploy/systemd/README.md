# systemd deployment (optional)

Run the bot **24/7 on your own VPS** — laptop not required. All paths are configurable; defaults assume install root **`/opt/world-cup-bot`**.

## Layout

| Path | Role |
|------|------|
| `/opt/world-cup-bot/` | Git clone (this repo) |
| `/opt/world-cup-bot/venv/` | `pip install -e ".[live]"` |
| `/opt/world-cup-bot/.env` | Your secrets (`cp .env.example .env`) |
| `/opt/world-cup-bot/bin/wc_run.sh` | Wrapper installed by `install-systemd.sh` |
| `/opt/world-cup-bot/data/local/shadow_ledger.jsonl` | Monitor profile: shadow `plan --record`, pnl-daily |
| `/opt/world-cup-bot/data/local/ledger.jsonl` | Trading profile: watch + live plan |
| `/opt/world-cup-bot/data/local/cross_venue_arb_ledger.jsonl` | Paper cross-venue arb intents (`--record`) |

Set the same `LEDGER_PATH` in `.env` as the file you use for `shadow-status`, or merge rows into one JSONL — split files make Phase 1 look stuck at “1 day” ([SHADOW.md](../../SHADOW.md)).
| `/opt/world-cup-bot/logs/cross_venue_reconcile.log` | Weekly `cross-venue-fill reconcile --json` |
| `/opt/world-cup-bot/logs/` | Timer stdout + cross-venue alerts |

Change the root with `--install-root` (e.g. `/home/you/world-cup-bot`).

## Two-VPS split (recommended)

Polymarket **order POST** is geo-blocked from the US. Split read vs write:

| Profile | Host example | `--profile` | What runs |
|---------|--------------|-------------|-----------|
| **Monitor** | US or any region | `monitor` | Cross-venue scan + **paper `--record`**, weekly **cross-venue reconcile**, shadow plan, scan, calendar, discover, **pnl-daily** (shadow ledger), conviction-staleness, fixture-check, **tournament-ops**, **match-shock discover/plan** (paper) |
| **Trading** | Non-US VPS (EU, etc.) | `trading` | Preflight, fill watch, live plan (Phase 4 — manual enable), **match-shock record** (manual), **match-shock live plan** (manual, gated), **cross-venue exec loop** (manual, gated) |

Single VPS outside the US can run **both** profiles if `preflight` geoblock passes.

See [SHADOW.md](../../SHADOW.md) for phase gates before live LP.

## Install

```bash
# 1. Clone + venv (adjust user/path as needed)
sudo mkdir -p /opt/world-cup-bot
sudo git clone https://github.com/cemini23/world-cup-bot.git /opt/world-cup-bot
cd /opt/world-cup-bot
cp .env.example .env   # edit with your keys
python3 -m venv venv
./venv/bin/pip install -e ".[live]"

# 2. Monitor host (alerts + shadow)
sudo bash deploy/systemd/install-systemd.sh --profile monitor --enable

# 3. Trading host (after SHADOW Phase 2+)
sudo bash deploy/systemd/install-systemd.sh --profile trading
# systemctl enable --now world-cup-bot-watch.service   # Phase 2
# systemctl enable --now world-cup-bot-live-plan.timer # Phase 4 — set WC_LIVE_PLAN_ACK=1 in .env first
```

## SHADOW phase → enable matrix

| Phase | Monitor VPS | Trading VPS |
|-------|-------------|-------------|
| 0 | cross-venue, scan, calendar timers | preflight timer |
| 1 | + shadow-plan timer (`--liquidity-gate` → shadow ledger) | — |
| 2 | + optional rewards-sync timer (L2 creds) | `world-cup-bot-watch.service` |
| 3 | — | preflight must PASS |
| 4 | — | `world-cup-bot-live-plan.timer` (manual); optional `world-cup-bot-cross-venue-exec.service` after paper soak |

**DRY_RUN / halt:** `world-cup-bot-live-plan.service` sets `WC_DRY_RUN=false` when the timer runs — removing `DRY_RUN=false` from `.env` alone does **not** stop live plan. Halt with `systemctl stop world-cup-bot-live-plan.timer` (see [SHADOW.md](../../SHADOW.md)). For Phase 2+ live fills, set `WC_DRY_RUN=false` in `.env.trading` for `world-cup-bot-watch.service` (unit no longer forces shadow mode).

## PnL vs rewards (split units)

| Unit | Command | When to enable |
|------|---------|----------------|
| `world-cup-bot-pnl-daily.timer` | `pnl --scope current` | Phase 1+ shadow — no L2 creds required |
| `world-cup-bot-cross-venue-reconcile.timer` | `cross-venue-fill reconcile --json` | Weekly Sun 08:00 UTC — after `--record` alerts |
| `world-cup-bot-rewards-sync.timer` | `rewards sync --record` | Phase 2+ after L2 creds on `.env` / `.env.trading` |

Live POST runs `assert_live_post_allowed()` when `DRY_RUN=false`. Kill-switch halts persist via `trading_halt` ledger events.

PnL reads the shadow ledger only. Rewards sync fails without authenticated CLOB access — keep it disabled until trading host is ready.

## Operator commands

```bash
/opt/world-cup-bot/bin/wc_run.sh cross-venue-scan --once --record
/opt/world-cup-bot/bin/wc_run.sh cross-venue-fill reconcile
/opt/world-cup-bot/bin/wc_run.sh cross-venue-pnl --refresh
/opt/world-cup-bot/bin/wc_run.sh shadow-status --min-phase 1
/opt/world-cup-bot/bin/wc_run.sh scan --conviction
/opt/world-cup-bot/bin/wc_run.sh plan --record --liquidity-gate
/opt/world-cup-bot/bin/wc_run.sh conviction-staleness --notify
/opt/world-cup-bot/bin/wc_run.sh fixture-check --notify
/opt/world-cup-bot/bin/wc_run.sh conviction-patch dr-output.md --stage
journalctl -u world-cup-bot-cross-venue -f
journalctl -u world-cup-bot-cross-venue-exec -f
tail -f /opt/world-cup-bot/logs/cross_venue_alerts.jsonl
tail -f /opt/world-cup-bot/logs/cross_venue_exec.log
```

## Update after git pull

```bash
cd /opt/world-cup-bot && git pull
sudo bash deploy/systemd/install-systemd.sh --profile monitor   # refresh units
sudo systemctl restart world-cup-bot-cross-venue.service
```

## Kill switch (live plan)

```bash
sudo systemctl disable --now world-cup-bot-live-plan.timer
# or: systemctl edit world-cup-bot-live-plan.service → Environment=WC_DRY_RUN=true
```

**Enable guard:** `world-cup-bot-live-plan.timer` refuses to run unless `WC_LIVE_PLAN_ACK=1` is set in `.env` (SHADOW Phase 4 operator sign-off).

## Match-shock (Module 8) — two-VPS split

| Unit | Profile | Auto-enable | Purpose |
|------|---------|-------------|---------|
| `world-cup-bot-tournament-ops.timer` | monitor | yes | Daily bundled health check |
| `world-cup-bot-match-shock-discover.timer` | monitor | yes | Weekly Gamma discovery → `match_markets.json` |
| `world-cup-bot-match-shock-plan.timer` | monitor | yes | Paper plan scan every 15m (Jun–Jul WC window) |
| `world-cup-bot-match-shock-record.service` | trading | **manual** | Live WS tape on egress (`WC_SHOCK_ENABLED=1`) |
| `world-cup-bot-match-shock-live-plan.timer` | trading | **manual** | Live ladder POST — requires `WC_MATCH_SHOCK_LIVE=1` + `WC_MATCH_SHOCK_LIVE_ACK=1` |

**Never** enable shock live POST on the same wallet as advance LP without operator sign-off and 3+ days paper ledger soak.

## Cross-venue auto-exec (Phase C) — trading VPS only

| Unit | Profile | Auto-enable | Purpose |
|------|---------|-------------|---------|
| `world-cup-bot-cross-venue.service` | monitor | yes | Scan + paper `--record` only (`WC_DRY_RUN=true`; no auto-exec) |
| `world-cup-bot-cross-venue-exec.service` | trading | **manual** | Scan loop + dual-leg POST when gap alerts fire |

Enable guard (same pattern as live plan / match-shock):

```bash
# .env.trading on egress VPS
WC_CROSS_VENUE_AUTO_EXEC=1
WC_CROSS_VENUE_EXEC_ACK=1
DRY_RUN=false

sudo systemctl enable --now world-cup-bot-cross-venue-exec.service
```

Service refuses start unless `WC_CROSS_VENUE_EXEC_ACK=1`. Runs `preflight` before the loop. Logs → `logs/cross_venue_exec.log`; `EXEC_AUTO` lines also go to syslog.

Kill switch: `systemctl disable --now world-cup-bot-cross-venue-exec.service` or unset `WC_CROSS_VENUE_AUTO_EXEC`.

```bash
# Monitor (paper shock)
systemctl status world-cup-bot-match-shock-plan.timer

# Egress (after paper soak)
systemctl enable --now world-cup-bot-match-shock-record.service
# systemctl enable --now world-cup-bot-match-shock-live-plan.timer  # after WC_MATCH_SHOCK_LIVE_ACK=1
```

Optional non-root install: `sudo bash deploy/systemd/install-systemd.sh --profile monitor --run-as-user wc-bot`

## Optional second env file

On the trading VPS, you can keep L2 keys in `.env.trading` only (loaded after `.env`). Not required if everything is in `.env`.
