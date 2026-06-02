#!/usr/bin/env bash
# sync_pmxt_football_to_librarian.sh
#
# Laptop orchestrator: rsync world-cup-bot shock scripts → cemini-librarian, run sync.
#
# Usage:
#   bash scripts/shock_backtest/sync_pmxt_football_to_librarian.sh --hours 24
#   bash scripts/shock_backtest/sync_pmxt_football_to_librarian.sh --from 2026-05-20 --to 2026-05-21
#   bash scripts/shock_backtest/sync_pmxt_football_to_librarian.sh --inspect-latest
#
# Pilot (6 hours, no backtest):
#   bash scripts/shock_backtest/sync_pmxt_football_to_librarian.sh --hours 6 --skip-backtest
#
# Env: LIBRARIAN_HOST (default cemini-librarian)
#      REMOTE_ROOT (default /opt/cemini-bulk/market-dataset/polymarket-orderbook)

set -euo pipefail

LIBRARIAN_HOST="${LIBRARIAN_HOST:-cemini-librarian}"
REMOTE_ROOT="${REMOTE_ROOT:-/opt/cemini-bulk/market-dataset/polymarket-orderbook}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WC_BOT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REMOTE_WC="$REMOTE_ROOT/_wc_bot_sync"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

ARGS=("$@")

log "Rsync shock pipeline → $LIBRARIAN_HOST:$REMOTE_WC"
ssh "$LIBRARIAN_HOST" "mkdir -p '$REMOTE_WC/scripts/shock_backtest' '$REMOTE_WC/world_cup_bot' '$REMOTE_WC/config' '$REMOTE_ROOT'"

rsync -az \
  "$WC_BOT_ROOT/scripts/shock_backtest/" \
  "$LIBRARIAN_HOST:$REMOTE_WC/scripts/shock_backtest/"

rsync -az \
  "$WC_BOT_ROOT/world_cup_bot/" \
  "$LIBRARIAN_HOST:$REMOTE_WC/world_cup_bot/"

rsync -az \
  "$WC_BOT_ROOT/config/shock_match.yaml" \
  "$LIBRARIAN_HOST:$REMOTE_WC/config/"

log "Run sync on librarian"
# shellcheck disable=SC2029
ssh "$LIBRARIAN_HOST" \
  "REMOTE_ROOT='$REMOTE_ROOT' WC_BOT_ROOT='$REMOTE_WC' bash '$REMOTE_WC/scripts/shock_backtest/run_pmxt_football_sync.sh' $(printf '%q ' "${ARGS[@]}")"

log "Done. Artifacts:"
log "  $REMOTE_ROOT/exports/shock-backtest/"
log "  $REMOTE_ROOT/sync_manifest.json"
