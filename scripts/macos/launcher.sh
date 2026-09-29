#!/usr/bin/env bash
set -euo pipefail
app_root="$(cd "$(dirname "$0")/../Resources/local-foundry" && pwd)"
state_root="$HOME/Library/Application Support/Local Foundry"
mkdir -p "$state_root"
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/python@3.12/bin:/usr/local/bin:/usr/local/opt/python@3.12/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export FOUNDRY_STATE_ROOT="$state_root"
export FOUNDRY_CONFIG="$state_root/.env"
export FOUNDRY_DATA="$state_root/data"
cd "$app_root"
foundry_python="${FOUNDRY_PYTHON:-python3.12}"
if ! command -v "$foundry_python" >/dev/null 2>&1 || ! command -v docker >/dev/null 2>&1; then
  osascript -e 'display alert "Prerequisites are missing" message "Install Python 3.12 and Docker Desktop before opening Local Foundry." as critical'
  exit 1
fi
log="$state_root/local-foundry.log"
exec >>"$log" 2>&1
on_error() {
  osascript -e 'display alert "Local Foundry stopped" message "See ~/Library/Application Support/Local Foundry/local-foundry.log. Your project data has been preserved." as critical'
}
trap on_error ERR
export FOUNDRY_PYTHON_EXECUTABLE
FOUNDRY_PYTHON_EXECUTABLE="$("$foundry_python" scripts/bootstrap-runtime.py)"
if ! docker info >/dev/null 2>&1; then
  open -a Docker
  for _ in {1..60}; do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
fi
docker info >/dev/null
missing=false
accounts_image="$("$FOUNDRY_PYTHON_EXECUTABLE" scripts/cache-accounts.py --print-image)"
for image in local-foundry-web:2 local-foundry-api:2 local-foundry-browser:4 postgres:17-bookworm "$accounts_image"; do
  docker image inspect "$image" >/dev/null 2>&1 || missing=true
done
if [[ "$missing" == true ]]; then docker load --input docker-images.tar; fi
"$FOUNDRY_PYTHON_EXECUTABLE" scripts/configure.py
scripts/start.sh
