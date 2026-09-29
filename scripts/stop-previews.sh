#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
foundry_state_root="${FOUNDRY_STATE_ROOT:-$PWD}"
foundry_data="${FOUNDRY_DATA:-$foundry_state_root/.data}"
shopt -s nullglob
for config_path in "$foundry_data"/projects/*/runtime.json; do
  docker compose -f "$config_path" down --timeout 8
done
echo "All app previews stopped. Database volumes are preserved."
