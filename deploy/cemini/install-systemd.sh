#!/usr/bin/env bash
# Install world-cup-bot Cemini systemd units (run as root on cemini-prod or cemini-egress-fi).
#
# Usage:
#   sudo bash deploy/cemini/install-systemd.sh --host prod
#   sudo bash deploy/cemini/install-systemd.sh --host egress
#   sudo bash deploy/cemini/install-systemd.sh --host prod --enable
#
set -euo pipefail

HOST=""
ENABLE=false
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

usage() {
  echo "Usage: $0 --host prod|egress [--enable]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
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

[[ -n "$HOST" ]] || usage
[[ "$HOST" == "prod" || "$HOST" == "egress" ]] || usage

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

if [[ ! -d /opt/cemini ]]; then
  echo "Missing /opt/cemini — CeminiSuite root required." >&2
  exit 1
fi

CEMINI_SYSTEMD="/opt/cemini/deploy/systemd"
mkdir -p /opt/cemini/scripts /opt/cemini/logs "$CEMINI_SYSTEMD"

install -m 0755 "${REPO_ROOT}/deploy/cemini/wc_run.sh" /opt/cemini/scripts/wc_run.sh

if [[ "$HOST" == "prod" ]]; then
  UNITS=(
    cemini-wc-cross-venue
    cemini-wc-shadow-plan
    cemini-wc-scan
    cemini-wc-calendar-guard
    cemini-wc-discover
    cemini-wc-pnl-daily
  )
else
  UNITS=(
    cemini-wc-preflight
    cemini-wc-watch
    cemini-wc-live-plan
  )
fi

for unit in "${UNITS[@]}"; do
  for ext in service timer; do
    src="${REPO_ROOT}/deploy/cemini/systemd/${unit}.${ext}"
    [[ -f "$src" ]] || continue
    dest="${CEMINI_SYSTEMD}/${unit}.${ext}"
    install -m 0644 "$src" "$dest"
    ln -sf "$dest" "/etc/systemd/system/${unit}.${ext}"
    echo "installed ${unit}.${ext}"
  done
done

touch /opt/cemini/logs/wc_cross_venue_alerts.jsonl
touch /opt/cemini/logs/wc_shadow_ledger.jsonl
touch /opt/cemini/logs/wc_ledger.jsonl

systemctl daemon-reload

if [[ "$ENABLE" == true ]]; then
  if [[ "$HOST" == "prod" ]]; then
    systemctl enable --now cemini-wc-cross-venue.service
    systemctl enable --now \
      cemini-wc-shadow-plan.timer \
      cemini-wc-scan.timer \
      cemini-wc-calendar-guard.timer \
      cemini-wc-discover.timer \
      cemini-wc-pnl-daily.timer
    echo "Prod Phase 0–1 units enabled."
  else
    systemctl enable --now cemini-wc-preflight.timer
    echo "Egress preflight timer enabled. Enable watch/live-plan manually after SHADOW gates."
  fi
else
  echo "Units installed (not enabled). Re-run with --enable or enable manually."
fi

echo "Smoke: /opt/cemini/scripts/wc_run.sh cross-venue-scan --once"
