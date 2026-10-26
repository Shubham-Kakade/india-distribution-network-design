#!/usr/bin/env bash
# Local setup for macOS / Linux (D-047): a virtual environment, the requirements, and a .env
# copied from .env.example with LLM_API_KEY left empty. An existing .env is never overwritten.
#
# Usage, from anywhere:   scripts/setup_local.sh [venv_dir]      (default: <repo>/.venv)
# Python other than python3:   PYTHON=python3.12 scripts/setup_local.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${1:-$ROOT/.venv}"
PY="${PYTHON:-python3}"

"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || { echo "Python 3.11 or later is needed; set PYTHON=..." >&2; exit 1; }

[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$ROOT/requirements.txt"
"$VENV/bin/python" -c "import pulp; assert 'PULP_CBC_CMD' in pulp.listSolvers(onlyAvailable=True)" \
  || { echo "CBC solver not found: check that pulp<4 is installed" >&2; exit 1; }

if [ -e "$ROOT/.env" ]; then
  echo ".env already exists: left unchanged"
else
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Created .env from .env.example (LLM_API_KEY is empty, so the agent runs offline)"
fi

echo "Done. Next:"
echo "  source \"$VENV/bin/activate\""
echo "  pytest -q && streamlit run app/streamlit_app.py"
