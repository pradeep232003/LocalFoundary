#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
for program in docker node npm; do
  if ! command -v "$program" >/dev/null; then
    echo "Missing $program. See README.md or WINDOWS.md for prerequisites."
    exit 1
  fi
done
foundry_python="${FOUNDRY_PYTHON:-python3.12}"
if ! command -v "$foundry_python" >/dev/null; then
  echo "Python 3.12 is required. See README.md (macOS) or WINDOWS.md (WSL2)."
  exit 1
fi
docker info >/dev/null
"$foundry_python" -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python scripts/configure.py
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
docker build -t local-foundry-web:2 template/frontend
docker build -t local-foundry-api:2 template/backend
.venv/bin/python scripts/cache-accounts.py
docker build -t local-foundry-browser:4 browser
foundry_state_root="${FOUNDRY_STATE_ROOT:-$PWD}"
foundry_data="${FOUNDRY_DATA:-$foundry_state_root/.data}"
docker compose -f "$foundry_data/builder-compose.json" up -d --wait
echo "Setup complete. Configure LOCAL_MODEL or a remote API key in $foundry_state_root/.env."
