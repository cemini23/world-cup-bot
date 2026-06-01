#!/usr/bin/env bash
# Wrapper for cross-platform threshold guard (Python is canonical; bash optional on Windows).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/scripts/check_hardcoded_thresholds.py" "$@"
