#!/usr/bin/env bash
# Bridge Cemini .env-polymarket → world-cup-bot env names; exec CLI.
# Installed to /opt/cemini/scripts/wc_run.sh by deploy/cemini/install-systemd.sh
set -euo pipefail
set -a
# shellcheck disable=SC1091
source /opt/cemini/.env
# shellcheck disable=SC1091
[[ -f /opt/cemini/.env-polymarket ]] && source /opt/cemini/.env-polymarket
set +a

export POLYMARKET_API_PASSPHRASE="${POLYMARKET_API_PASSPHRASE:-${POLYMARKET_PASSPHRASE:-}}"
export POLYMARKET_PRIVATE_KEY="${POLYMARKET_PRIVATE_KEY:-${POLYGON_PRIVATE_KEY:-}}"
export POLYMARKET_FUNDER_ADDRESS="${POLYMARKET_FUNDER_ADDRESS:-${POLYGON_ADDRESS:-}}"
export POLYMARKET_POLY_ADDRESS="${POLYMARKET_POLY_ADDRESS:-${POLYGON_ADDRESS:-}}"
export DRY_RUN="${WC_DRY_RUN:-true}"
export LEDGER_PATH="${WC_LEDGER_PATH:-/opt/cemini/logs/wc_ledger.jsonl}"
export LOG_LEVEL="${WC_LOG_LEVEL:-INFO}"

WC_VENV="/opt/world-cup-bot/venv/bin/world-cup-bot"
[[ -x "$WC_VENV" ]] || {
  echo "missing $WC_VENV — pip install -e /opt/world-cup-bot/repo[live]" >&2
  exit 1
}
exec "$WC_VENV" "$@"
