#!/usr/bin/env bash
# K107 — LP safety deep-research reminder (Gemini 03-team-lp-risk).
# Run before conviction.yaml edits during pre-kickoff inflow window.
# Shadow-only: prints research bundle path; does not auto-patch YAML.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER="${REPO}/data/local/k107_lp_safety_last_run.txt"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "=== K107 LP safety DR — ${STAMP} UTC ==="
echo "Prompt: ${REPO}/prompts/gemini-deep-research/03-team-lp-risk.md"
echo ""
echo "Run weekly through tournament window. Review output before editing config/conviction.yaml."
echo ""

if [[ -x "${REPO}/../bin/wc_run.sh" ]]; then
  WC_RUN="${REPO}/../bin/wc_run.sh"
elif [[ -x "/opt/cemini/scripts/wc_run.sh" ]]; then
  WC_RUN="/opt/cemini/scripts/wc_run.sh"
else
  echo "wc_run.sh not found — run from cemini-prod: bash /opt/cemini/scripts/wc_run.sh research bundle team-lp-risk --team <Team>"
  mkdir -p "$(dirname "${MARKER}")"
  echo "${STAMP}" > "${MARKER}"
  exit 0
fi

echo "Example (single team):"
echo "  bash ${WC_RUN} research bundle team-lp-risk --team Brazil"
echo ""
echo "Optional staleness sweep:"
echo "  bash ${WC_RUN} conviction-staleness --notify"
echo ""

mkdir -p "$(dirname "${MARKER}")"
echo "${STAMP}" > "${MARKER}"
echo "Marked last run: ${MARKER}"
