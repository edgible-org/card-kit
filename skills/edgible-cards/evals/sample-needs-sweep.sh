#!/usr/bin/env bash
# Draw N unused needs-sweep ids without replacement (ledger outside card-kit).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${EDGIBLE_NEEDS_SWEEP_DIR:-$HOME/edgible-needs-sweep}"
exec python3 "$HERE/make-needs-sweep.py" --data-dir "$DATA_DIR" "$@"
