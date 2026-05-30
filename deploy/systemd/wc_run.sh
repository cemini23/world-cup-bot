#!/usr/bin/env bash
# Load .env from install root and exec world-cup-bot CLI.
# Installed to @INSTALL_ROOT@/bin/wc_run.sh by deploy/systemd/install-systemd.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="${WC_INSTALL_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

set -a
# shellcheck disable=SC1091
[[ -f "$INSTALL_ROOT/.env" ]] && source "$INSTALL_ROOT/.env"
# Optional extra secrets file (e.g. trading-only keys on a second VPS)
# shellcheck disable=SC1091
[[ -f "$INSTALL_ROOT/.env.trading" ]] && source "$INSTALL_ROOT/.env.trading"
set +a

# Common alias names from other Polymarket tooling
export POLYMARKET_API_PASSPHRASE="${POLYMARKET_API_PASSPHRASE:-${POLYMARKET_PASSPHRASE:-}}"
export POLYMARKET_PRIVATE_KEY="${POLYMARKET_PRIVATE_KEY:-${POLYGON_PRIVATE_KEY:-}}"
export POLYMARKET_FUNDER_ADDRESS="${POLYMARKET_FUNDER_ADDRESS:-${POLYGON_ADDRESS:-}}"
export POLYMARKET_POLY_ADDRESS="${POLYMARKET_POLY_ADDRESS:-${POLYGON_ADDRESS:-}}"
export DRY_RUN="${WC_DRY_RUN:-true}"
export LEDGER_PATH="${WC_LEDGER_PATH:-$INSTALL_ROOT/data/local/ledger.jsonl}"
export LOG_LEVEL="${WC_LOG_LEVEL:-INFO}"

CLI="$INSTALL_ROOT/venv/bin/world-cup-bot"
[[ -x "$CLI" ]] || {
  echo "missing $CLI — run: python3 -m venv $INSTALL_ROOT/venv && pip install -e '$INSTALL_ROOT[live]'" >&2
  exit 1
}
exec "$CLI" "$@"
