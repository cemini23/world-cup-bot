#!/usr/bin/env bash
# Phase 0 shadow bootstrap — run from repo root after pip install -e ".[dev]"
set -euo pipefail

echo "== World Cup Bot shadow setup (Phase 0) =="
echo

echo "[1/5] Preflight (shadow-safe, skip auth if no L2)..."
world-cup-bot preflight --skip-auth || true
echo

echo "[2/5] Gamma scan + conviction gate..."
world-cup-bot scan --conviction --liquidity | head -40
echo

echo "[3/5] Risk gates (K102 — on by default; portfolio gates defer in DRY_RUN)..."
world-cup-bot risk-status || true
echo

echo "[4/5] Shadow status..."
world-cup-bot shadow-status --min-phase 0 --skip-auth || true
echo

echo "[5/5] Dry-run plan (record to ledger)..."
world-cup-bot plan --record --liquidity-gate || true
echo

echo "Next steps (see SHADOW.md):"
echo "  - Run plan --record --liquidity-gate on >=3 separate calendar days"
echo "  - Set L2 creds in .env; WC_BANKROLL_FROM_WALLET=1 (default) for live % gates"
echo "  - Set L2 creds in .env, then: world-cup-bot watch --verbose --record"
echo "  - preflight from non-US egress before DRY_RUN=false"
echo "  - world-cup-bot shadow-status --min-phase 3"
