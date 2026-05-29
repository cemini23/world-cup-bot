#!/usr/bin/env bash
# Fail CI if price/mid thresholds are hardcoded in hot-path modules (must live in config/*.yaml).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOT_PATH=(world_cup_bot/scanner.py world_cup_bot/quoter.py world_cup_bot/fill_handler.py)

PATTERN='(mid\s*[><=!]+\s*0\.|>\s*0\.90|<\s*0\.10)'

if rg -n "$PATTERN" "${HOT_PATH[@]}" 2>/dev/null; then
  echo "FAIL: hardcoded mid/threshold in hot-path — move to config/operating.yaml or config/conviction.yaml"
  exit 1
fi

echo "OK: no hardcoded mid thresholds in hot-path modules"
