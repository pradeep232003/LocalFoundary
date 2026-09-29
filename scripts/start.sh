#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
foundry_state_root="${FOUNDRY_STATE_ROOT:-$PWD}"
foundry_data="${FOUNDRY_DATA:-$foundry_state_root/.data}"
foundry_python="${FOUNDRY_PYTHON_EXECUTABLE:-.venv/bin/python}"
if [[ ! -x "$foundry_python" || ! -f "$foundry_data/builder-compose.json" ]]; then
  echo "Run ./scripts/setup.sh first."
  exit 1
fi
docker compose -f "$foundry_data/builder-compose.json" up -d --wait --pull never
exec "$foundry_python" scripts/serve.py
