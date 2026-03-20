#!/usr/bin/env bash
# Start kobold-sandbox API server on port 5002,
# connecting to KoboldCPP backend at localhost:5001.
#
# Usage:
#   bash serve-5002.sh            # use script dir as sandbox root
#   bash serve-5002.sh /path/to   # use custom sandbox root

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${1:-$SCRIPT_DIR}"

export SANDBOX_HOST="127.0.0.1"
export SANDBOX_PORT=5002
export SANDBOX_ROOT="$ROOT"
export KOBOLD_URL="http://localhost:5001"

# Initialise sandbox if not already done
if [ ! -f "$ROOT/.sandbox/state.json" ]; then
  echo "Sandbox not initialised in $ROOT — running init..."
  PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH:-}" \
    python -m kobold_sandbox.cli init --root "$ROOT" --kobold-url "$KOBOLD_URL"
fi

echo "Starting kobold-sandbox server on http://${SANDBOX_HOST}:${SANDBOX_PORT}"
echo "KoboldCPP backend: ${KOBOLD_URL}"
echo "Sandbox root: ${ROOT}"
echo "---"

PYTHONPATH="${SCRIPT_DIR}/src:${PYTHONPATH:-}" \
exec python -c "
import os, uvicorn
from kobold_sandbox.server import create_app

app = create_app(os.environ['SANDBOX_ROOT'])
uvicorn.run(app, host=os.environ['SANDBOX_HOST'], port=int(os.environ['SANDBOX_PORT']))
"
