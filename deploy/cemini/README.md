# Cemini operator deployment

**Private ops path** for [CeminiSuite](https://github.com/cemini23) hosts — not required for public forks.

Matches the existing PM/Kalshi pattern: units in `/opt/cemini/deploy/systemd/`, secrets in `/opt/cemini/.env` + `.env-polymarket`, logs in `/opt/cemini/logs/`.

## Layout

| Path | Role |
|------|------|
| `/opt/world-cup-bot/repo` | Git clone of this repo |
| `/opt/world-cup-bot/venv` | `pip install -e ".[live]"` |
| `/opt/cemini/scripts/wc_run.sh` | Env bridge → `world-cup-bot` CLI |
| `/opt/cemini/deploy/systemd/cemini-wc-*` | Unit files (symlinked to `/etc/systemd/system/`) |

## Two-host split

| Host | Enable | Modules |
|------|--------|---------|
| **cemini-prod** (US) | `--host prod` | Cross-venue loop, shadow plan, scan, calendar, discover, pnl |
| **cemini-egress-fi** (FI) | `--host egress` | Preflight, watch, live plan (Phase 4 — manual) |

PM order **POST** is geo-blocked from the US. See [SHADOW.md](../../SHADOW.md) for phase gates.

## Install (server-Claude or root shell)

```bash
# 1. Repo + venv (once per host)
sudo useradd -r -m -d /opt/world-cup-bot -s /usr/sbin/nologin worldcup 2>/dev/null || true
sudo -u worldcup git clone https://github.com/cemini23/world-cup-bot.git /opt/world-cup-bot/repo
sudo -u worldcup python3 -m venv /opt/world-cup-bot/venv
sudo -u worldcup /opt/world-cup-bot/venv/bin/pip install -e "/opt/world-cup-bot/repo[live]"

# 2. Systemd (from repo root after git pull)
cd /opt/world-cup-bot/repo
sudo bash deploy/cemini/install-systemd.sh --host prod --enable    # on cemini-prod
sudo bash deploy/cemini/install-systemd.sh --host egress           # on egress-fi (enable watch after Phase 2)
```

## Enable matrix (SHADOW phases)

| Phase | prod | egress-fi |
|-------|------|-----------|
| 0 | `cemini-wc-cross-venue`, scan, calendar timers | preflight timer |
| 1 | + shadow-plan timer | — |
| 2 | — | `cemini-wc-watch.service` |
| 3 | — | preflight must PASS |
| 4 | — | `cemini-wc-live-plan.timer` (manual) |

## Operator commands

```bash
/opt/cemini/scripts/wc_run.sh cross-venue-scan --once
/opt/cemini/scripts/wc_run.sh scan --conviction
/opt/cemini/scripts/wc_run.sh plan --record
journalctl -u cemini-wc-cross-venue -f
tail -f /opt/cemini/logs/wc_cross_venue_alerts.jsonl
```

## Update after git push

```bash
cd /opt/world-cup-bot/repo && sudo -u worldcup git pull
sudo bash deploy/cemini/install-systemd.sh --host prod   # refresh unit files
sudo systemctl restart cemini-wc-cross-venue.service   # if ExecStart changed
```

## Logs

| File | Content |
|------|---------|
| `wc_cross_venue_alerts.jsonl` | Module 6 ALERT / SLUG_CHANGE |
| `wc_shadow_ledger.jsonl` | Shadow plan intents (prod) |
| `wc_ledger.jsonl` | Live fills (egress-fi) |
| `cron_wc_*.log` | Timer stdout |

## Kill switch (live plan)

```bash
sudo systemctl disable --now cemini-wc-live-plan.timer
# or override: systemctl edit cemini-wc-live-plan.service → Environment=WC_DRY_RUN=true
```

OSINT brief (full narrative): `briefs/2026-05-29_wc-full-stack-cemini-systemd.md` in the Cemini OSINT workspace.
