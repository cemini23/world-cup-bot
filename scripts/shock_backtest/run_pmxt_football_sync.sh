#!/usr/bin/env bash
# run_pmxt_football_sync.sh — run ON cemini-librarian (or any Linux host with disk).
#
# Invoked by sync_pmxt_football_to_librarian.sh after rsync, or directly:
#   REMOTE_ROOT=/opt/cemini-bulk/market-dataset/polymarket-orderbook \
#   WC_BOT_ROOT=/opt/cemini-bulk/market-dataset/polymarket-orderbook/_wc_bot_sync \
#   bash run_pmxt_football_sync.sh --hours 24

set -euo pipefail

REMOTE_ROOT="${REMOTE_ROOT:-/opt/cemini-bulk/market-dataset/polymarket-orderbook}"
WC_BOT_ROOT="${WC_BOT_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
ARCHIVE_BASE="${ARCHIVE_BASE:-https://r2v2.pmxt.dev}"
PY="${PY:-python3}"
if [[ -x "${WC_BOT_ROOT}/.venv/bin/python" ]]; then
  PY="${WC_BOT_ROOT}/.venv/bin/python"
fi
HOURS=24
FROM_DATE=""
TO_DATE=""
SKIP_BACKTEST=0
KEEP_PARQUET=0
INSPECT_LATEST=0
CONVERT_ONLY=0
SLOT=""

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hours) HOURS="$2"; shift 2 ;;
    --from) FROM_DATE="$2"; shift 2 ;;
    --to) TO_DATE="$2"; shift 2 ;;
    --slot) SLOT="$2"; shift 2 ;;
    --convert-only) CONVERT_ONLY=1; shift ;;
    --skip-backtest) SKIP_BACKTEST=1; shift ;;
    --keep-parquet) KEEP_PARQUET=1; shift ;;
    --inspect-latest) INSPECT_LATEST=1; shift ;;
    --root) REMOTE_ROOT="$2"; shift 2 ;;
    --wc-bot-root) WC_BOT_ROOT="$2"; shift 2 ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
done

export PYTHONPATH="${WC_BOT_ROOT}${PYTHONPATH:+:$PYTHONPATH}"
SHOCK="${WC_BOT_ROOT}/scripts/shock_backtest"
CONFIG="${WC_BOT_ROOT}/config/shock_match.yaml"

ensure_pyarrow() {
  if "$PY" -c "import pyarrow, yaml" 2>/dev/null; then
    return 0
  fi
  local venv="${WC_BOT_ROOT}/.venv"
  log "deps missing — bootstrapping venv at $venv"
  python3 -m venv "$venv"
  "$venv/bin/pip" install -q pyarrow pyyaml
  PY="$venv/bin/python"
}

ensure_pyarrow

staging="$REMOTE_ROOT/pmxt-mirror/staging/parquet"
raw_jsonl="$REMOTE_ROOT/exports/shock-backtest/raw/pmxt_events.jsonl"
tapes_dir="$REMOTE_ROOT/exports/shock-backtest/tapes"
manifest="$REMOTE_ROOT/sync_manifest.json"
dist="$REMOTE_ROOT/exports/shock-backtest/shock_distributions.json"

mkdir -p "$staging" "$(dirname "$raw_jsonl")" "$tapes_dir" "$REMOTE_ROOT/pmxt-mirror/raw"
[[ -f "$manifest" ]] || echo '{"hours":{}}' > "$manifest"

if [[ "$INSPECT_LATEST" -eq 1 ]]; then
  latest=$(ls -1t "$staging"/*.parquet 2>/dev/null | head -1 || true)
  [[ -n "$latest" ]] || { log "No parquet in $staging"; exit 1; }
  "$PY" "$SHOCK/pmxt_parquet_to_jsonl.py" --inspect "$latest"
  exit 0
fi

build_hours() {
  if [[ -n "$FROM_DATE" ]]; then
    end="${TO_DATE:-$(date -u '+%Y-%m-%d')}"
    current="$FROM_DATE"
    while :; do
      for h in $(seq -w 0 23); do
        echo "${current}T${h}"
      done
      [[ "$current" == "$end" ]] && break
      current=$(date -u -d "$current + 1 day" '+%Y-%m-%d')
      [[ "$current" > "$end" ]] && break
    done
  else
    for i in $(seq 0 $((HOURS - 1))); do
      date -u -d "${i} hours ago" '+%Y-%m-%dT%H'
    done
  fi
}

hours_file=$(mktemp)
if [[ -n "$SLOT" ]]; then
  echo "$SLOT" > "$hours_file"
elif [[ "$CONVERT_ONLY" -eq 1 && -z "$FROM_DATE" ]]; then
  ls -1 "$staging"/polymarket_orderbook_*.parquet 2>/dev/null \
    | sed -n 's|.*/polymarket_orderbook_\(.*\)\.parquet|\1|p' \
    | sort -u > "$hours_file" || true
else
  build_hours | sort -u > "$hours_file"
fi
log "Processing $(wc -l < "$hours_file" | tr -d ' ') UTC hour(s)"

while read -r slot; do
  [[ -z "$slot" ]] && continue
  if "$PY" -c "import json; m=json.load(open('$manifest')); raise SystemExit(0 if '$slot' in m.get('hours',{}) else 1)" 2>/dev/null; then
    log "skip manifest: $slot"
    continue
  fi

  fname="polymarket_orderbook_${slot}.parquet"
  url="${ARCHIVE_BASE}/${fname}"
  dest="$staging/$fname"

  if [[ "$CONVERT_ONLY" -eq 0 ]]; then
    log "GET $url"
    if ! curl -fsSL --retry 3 --retry-delay 10 -o "$dest.part" "$url"; then
      log "WARN failed download $url"
      rm -f "$dest.part"
      continue
    fi
    if ! head -c 4 "$dest.part" | grep -q 'PAR1'; then
      log "WARN not parquet (bad URL or HTML) — $url"
      rm -f "$dest.part"
      continue
    fi
    mv "$dest.part" "$dest"
  elif [[ ! -f "$dest" ]]; then
    log "WARN missing parquet for convert-only: $dest"
    continue
  fi

  log "convert $fname"
  if ! "$PY" "$SHOCK/pmxt_parquet_to_jsonl.py" "$dest" --out "$raw_jsonl" --append --config "$CONFIG"; then
    log "WARN convert failed — run: pmxt_parquet_to_jsonl.py --inspect $dest"
    continue
  fi

  "$PY" - <<PY
import json, datetime
p = "$manifest"
m = json.load(open(p))
m.setdefault("hours", {})["$slot"] = {
    "file": "$fname",
    "at": datetime.datetime.utcnow().isoformat() + "Z",
}
json.dump(m, open(p, "w"), indent=2)
PY

  if [[ "$KEEP_PARQUET" -eq 0 ]]; then
    rm -f "$dest"
  else
    mv "$dest" "$REMOTE_ROOT/pmxt-mirror/raw/"
  fi
done < "$hours_file"
rm -f "$hours_file"

log "export shock tapes"
"$PY" "$SHOCK/export_pmxt_shock_tapes.py" "$raw_jsonl" --out-dir "$tapes_dir" --per-slug --config "$CONFIG" || true

if [[ "$SKIP_BACKTEST" -eq 0 && -f "$tapes_dir/combined.jsonl" ]]; then
  log "bucket backtest"
  "$PY" "$SHOCK/run_bucket_backtest.py" "$tapes_dir/combined.jsonl" \
    --out-distributions "$dist" --replay --config "$CONFIG" \
    | tee "$REMOTE_ROOT/exports/shock-backtest/replay_report.json" || true
fi

log "complete raw=$raw_jsonl dist=$dist"
