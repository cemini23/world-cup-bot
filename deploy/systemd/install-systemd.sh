#!/usr/bin/env bash
# Install world-cup-bot systemd units (Linux VPS). Run as root.
#
# Usage:
#   sudo bash deploy/systemd/install-systemd.sh --install-root /opt/world-cup-bot --profile monitor
#   sudo bash deploy/systemd/install-systemd.sh --install-root /opt/world-cup-bot --profile trading
#   sudo bash deploy/systemd/install-systemd.sh --install-root /opt/world-cup-bot --profile monitor --enable
#
set -euo pipefail

INSTALL_ROOT="/opt/world-cup-bot"
PROFILE=""
ENABLE=false
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
  echo "Usage: $0 [--install-root PATH] --profile monitor|trading [--enable]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root)
      INSTALL_ROOT="${2:-}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --enable)
      ENABLE=true
      shift
      ;;
    -h | --help)
      usage
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      ;;
  esac
done

[[ -n "$PROFILE" ]] || usage
[[ "$PROFILE" == "monitor" || "$PROFILE" == "trading" ]] || usage

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

mkdir -p "$INSTALL_ROOT/bin" "$INSTALL_ROOT/data/local" "$INSTALL_ROOT/logs"

install -m 0755 "${REPO_ROOT}/deploy/systemd/wc_run.sh" "$INSTALL_ROOT/bin/wc_run.sh"

if [[ "$PROFILE" == "monitor" ]]; then
  UNITS=(
    world-cup-bot-cross-venue
    world-cup-bot-shadow-plan
    world-cup-bot-scan
    world-cup-bot-calendar-guard
    world-cup-bot-discover
    world-cup-bot-pnl-daily
    world-cup-bot-rewards-sync
    world-cup-bot-conviction-staleness
    world-cup-bot-fixture-check
  )
else
  UNITS=(
    world-cup-bot-preflight
    world-cup-bot-watch
    world-cup-bot-live-plan
  )
fi

for unit in "${UNITS[@]}"; do
  for ext in service timer; do
    src="${REPO_ROOT}/deploy/systemd/units/${unit}.${ext}"
    [[ -f "$src" ]] || continue
    dest="/etc/systemd/system/${unit}.${ext}"
    sed "s|@INSTALL_ROOT@|${INSTALL_ROOT}|g" "$src" >"$dest"
    chmod 0644 "$dest"
    echo "installed ${unit}.${ext} → $dest"
  done
done

touch "$INSTALL_ROOT/logs/cross_venue_alerts.jsonl"
touch "$INSTALL_ROOT/logs/cron_pnl.log"
touch "$INSTALL_ROOT/logs/cron_rewards.log"
touch "$INSTALL_ROOT/data/local/shadow_ledger.jsonl"
touch "$INSTALL_ROOT/data/local/ledger.jsonl"

systemctl daemon-reload

if [[ "$ENABLE" == true ]]; then
  if [[ "$PROFILE" == "monitor" ]]; then
    systemctl enable --now world-cup-bot-cross-venue.service
    systemctl enable --now \
      world-cup-bot-shadow-plan.timer \
      world-cup-bot-scan.timer \
      world-cup-bot-calendar-guard.timer \
      world-cup-bot-discover.timer \
      world-cup-bot-pnl-daily.timer \
      world-cup-bot-conviction-staleness.timer \
      world-cup-bot-fixture-check.timer
    echo "Monitor profile enabled (read-only + shadow timers)."
    echo "Rewards sync unit installed but timer NOT enabled — enable after Phase 2 + L2 creds:"
    echo "  systemctl enable --now world-cup-bot-rewards-sync.timer"
  else
    systemctl enable --now world-cup-bot-preflight.timer
    echo "Trading profile: preflight timer enabled. Enable watch/live-plan after SHADOW.md gates."
  fi
else
  echo "Units installed (not enabled). Re-run with --enable or systemctl enable manually."
fi

echo "Smoke: $INSTALL_ROOT/bin/wc_run.sh cross-venue-scan --once"
