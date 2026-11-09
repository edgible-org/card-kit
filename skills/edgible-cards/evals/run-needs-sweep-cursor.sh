#!/usr/bin/env bash
# Sample (optional) and run a needs sweep with the Cursor Agent harness.
# Results and ledger live under EDGIBLE_NEEDS_SWEEP_DIR (default ~/edgible-needs-sweep).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${EDGIBLE_NEEDS_SWEEP_DIR:-$HOME/edgible-needs-sweep}"
N=10
SEED="$(date +%Y%m%d)"
MODEL=""
JUDGE_MODEL="sonnet"
JUDGE_HARNESS="claude"
SAMPLE_FIRST=1
ONLY=()
OUT=""
EXTRA=()

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

  --seed N          sample seed (default: today's YYYYMMDD)
  --sample N        how many needs to draw (default: 10)
  --model ID        Cursor agent --model id (required for a real run)
  --judge-model M   judge model (default: sonnet for claude judge)
  --judge-harness   claude (default) or cursor
  --out DIR         results directory
  --only ID…        skip sampling; score these ids only
  --no-sample       use last-sample-<model>.json instead of drawing
  -h, --help        this help

Without-replacement sampling is per --model (each answer model has its own pool).

Environment: EDGIBLE_NEEDS_SWEEP_DIR (default ~/edgible-needs-sweep)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed) SEED="$2"; shift 2 ;;
    --sample) N="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
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

if [[ -z "$MODEL" && ${#ONLY[@]} -eq 0 ]]; then
  echo "--model is required (without-replacement pools are per answer model)" >&2
  exit 1
fi

if [[ ! -f "$HERE/needs-sweep.yaml" ]]; then
  python3 "$HERE/make-needs-sweep.py" --write-set
fi

MODEL_SLUG="${MODEL:-default}"
MODEL_SLUG="${MODEL_SLUG//\//-}"
LAST="$DATA_DIR/last-sample-${MODEL_SLUG}.json"

IDS=()
if [[ ${#ONLY[@]} -gt 0 ]]; then
  IDS=("${ONLY[@]}")
elif [[ "$SAMPLE_FIRST" -eq 1 ]]; then
  python3 "$HERE/make-needs-sweep.py" --data-dir "$DATA_DIR" --model "$MODEL" --sample "$N" --seed "$SEED"
  mapfile -t IDS < <(python3 -c "import json,pathlib; print('\\n'.join(json.loads(pathlib.Path('$LAST').read_text())['ids']))")
else
  [[ -f "$LAST" ]] || { echo "no $LAST; run without --no-sample" >&2; exit 1; }
  mapfile -t IDS < <(python3 -c "import json,pathlib; print('\\n'.join(json.loads(pathlib.Path('$LAST').read_text())['ids']))")
  SEED="$(python3 -c "import json,pathlib; print(json.loads(pathlib.Path('$LAST').read_text()).get('seed','$SEED'))")"
fi

[[ ${#IDS[@]} -gt 0 ]] || { echo "no ids to run" >&2; exit 1; }

if [[ -z "$OUT" ]]; then
  OUT="$DATA_DIR/results/needs-sweep-cursor-${MODEL_SLUG}-$(date +%F)-seed${SEED}"
fi

if [[ "$JUDGE_HARNESS" == "cursor" && "$JUDGE_MODEL" == "sonnet" ]]; then
  JUDGE_MODEL="${MODEL:-composer-2.5}"
fi
ARGS=(
  --set "$HERE/needs-sweep.yaml"
  --out "$OUT"
  --only "${IDS[@]}"
  --judge-model "$JUDGE_MODEL"
  --judge-harness "$JUDGE_HARNESS"
)
[[ -n "$MODEL" ]] && ARGS+=(--model "$MODEL")

LOG="${OUT}.log"
# When started under nohup/redirect, the invoker may already tee elsewhere; still print
# a monitor hint for whoever kicked off the batch (human or Cursor agent).
echo "ids: ${IDS[*]}"
echo "out: $OUT"
echo "monitor: tail -f $LOG"
echo "report: $OUT/report.md"
exec python3 "$HERE/run-needs-sweep-cursor.py" "${ARGS[@]}" ${EXTRA[@]+"${EXTRA[@]}"}
