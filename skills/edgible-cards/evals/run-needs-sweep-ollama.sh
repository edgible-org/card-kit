#!/usr/bin/env bash
# Sample (optional) and run a needs sweep with a local Ollama answering harness.
# Results and ledger live under EDGIBLE_NEEDS_SWEEP_DIR (default ~/edgible-needs-sweep).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${EDGIBLE_NEEDS_SWEEP_DIR:-$HOME/edgible-needs-sweep}"
N=3
SEED="$(date +%Y%m%d)"
MODEL="${OLLAMA_MODEL:-qwen3.5:9b}"
BASE_URL="${OLLAMA_HOST:-http://127.0.0.1:11434}"
JUDGE_MODEL="composer-2.5"
JUDGE_HARNESS="cursor"
SAMPLE_FIRST=1
ONLY=()
OUT=""
EXTRA=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

  --seed N          sample seed (default: today's YYYYMMDD)
  --sample N        how many needs to draw (default: 3)
  --model TAG       Ollama model tag (default: qwen3.5:9b or \$OLLAMA_MODEL)
  --base-url URL    Ollama base (default: \$OLLAMA_HOST or http://127.0.0.1:11434)
  --judge-model M   Cursor judge model (default: composer-2.5)
  --judge-harness   cursor (default), claude, or none
  --out DIR         results directory
  --only ID…        skip sampling; score these ids only
  --no-sample       use last-sample-ollama-<model>.json
  -h, --help        this help

Answer harness is local Ollama (no Cursor answer quota). Default judge is
Composer via Cursor so Other Models is not burned.

Ledger key is ollama/<model> so it does not collide with Cursor model pools.

Environment: EDGIBLE_NEEDS_SWEEP_DIR, OLLAMA_HOST, OLLAMA_MODEL
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED="$2"; shift 2 ;;
    --sample) N="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --judge-model) JUDGE_MODEL="$2"; shift 2 ;;
    --judge-harness) JUDGE_HARNESS="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --no-sample) SAMPLE_FIRST=0; shift ;;
    --only)
      shift
      while [[ $# -gt 0 && "$1" != --* ]]; do ONLY+=("$1"); shift; done
      SAMPLE_FIRST=0
      ;;
    -h|--help) usage; exit 0 ;;
    *) EXTRA+=("$1"); shift ;;
  esac
done

mkdir -p "$DATA_DIR"

if [[ ! -f "$HERE/needs-sweep.yaml" ]]; then
  python3 "$HERE/make-needs-sweep.py" --write-set
fi

# Per-harness ledger: prefix so Cursor composer and Ollama qwen pools stay separate.
LEDGER_MODEL="ollama/${MODEL}"
MODEL_SLUG="${MODEL//\//-}"
LAST="$DATA_DIR/last-sample-ollama-${MODEL_SLUG}.json"

IDS=()
if [[ ${#ONLY[@]} -gt 0 ]]; then
  IDS=("${ONLY[@]}")
elif [[ "$SAMPLE_FIRST" -eq 1 ]]; then
  python3 "$HERE/make-needs-sweep.py" --data-dir "$DATA_DIR" --model "$LEDGER_MODEL" --sample "$N" --seed "$SEED"
  # make-needs-sweep writes last-sample-<slug>.json from --model (same path as $LAST when slug matches)
  LAST_GEN="$DATA_DIR/last-sample-${LEDGER_MODEL//\//-}.json"
  if [[ -f "$LAST_GEN" && "$LAST_GEN" != "$LAST" ]]; then
    cp -f "$LAST_GEN" "$LAST"
  fi
  [[ -f "$LAST" ]] || LAST="$LAST_GEN"
  mapfile -t IDS < <(python3 -c "import json,pathlib; print('\\n'.join(json.loads(pathlib.Path('$LAST').read_text())['ids']))")
else
  [[ -f "$LAST" ]] || { echo "no $LAST; run without --no-sample" >&2; exit 1; }
  mapfile -t IDS < <(python3 -c "import json,pathlib; print('\\n'.join(json.loads(pathlib.Path('$LAST').read_text())['ids']))")
  SEED="$(python3 -c "import json,pathlib; print(json.loads(pathlib.Path('$LAST').read_text()).get('seed','$SEED'))")"
fi

[[ ${#IDS[@]} -gt 0 ]] || { echo "no ids to run" >&2; exit 1; }

if [[ -z "$OUT" ]]; then
  OUT="$DATA_DIR/results/needs-sweep-ollama-${MODEL_SLUG}-$(date +%F)-seed${SEED}"
fi

ARGS=(
  --set "$HERE/needs-sweep.yaml"
  --out "$OUT"
  --only "${IDS[@]}"
  --model "$MODEL"
  --base-url "$BASE_URL"
  --judge-model "$JUDGE_MODEL"
  --judge-harness "$JUDGE_HARNESS"
)

LOG="${OUT}.log"
echo "ids: ${IDS[*]}"
echo "out: $OUT"
echo "monitor: tail -f $LOG"
echo "report: $OUT/report.md"
exec python3 "$HERE/run-needs-sweep-ollama.py" "${ARGS[@]}" ${EXTRA[@]+"${EXTRA[@]}"}
