#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This end-to-end smoke test must run on macOS."
  exit 1
fi
for program in docker node npm curl; do
  if ! command -v "$program" >/dev/null; then
    echo "Missing $program. Complete the prerequisites in README.md first."
    exit 1
  fi
done
if [[ ! -x .venv/bin/python ]]; then
  echo "Run ./scripts/setup.sh before the Mac smoke test."
  exit 1
fi
docker info >/dev/null

echo "Mac: $(sw_vers -productVersion) · $(uname -m)"
echo "Docker: $(docker version --format '{{.Server.Version}}')"
echo "Node: $(node --version)"

PYTHONPATH=backend .venv/bin/python -m pytest tests -q
PYTHONPATH=backend FOUNDRY_LIVE_DOCKER=1 .venv/bin/python -m pytest tests/test_live_acceptance.py -q
npm --prefix frontend run build

smoke_root="$(mktemp -d "${TMPDIR:-/tmp}/local-foundry-smoke.XXXXXX")"
smoke_id="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(16))')"
smoke_source="$smoke_root/source"
mkdir -p "$smoke_source"
cp -R template/. "$smoke_source/"

cleanup() {
  if [[ -f "$smoke_source/compose.json" ]]; then
    docker compose -f "$smoke_source/compose.json" down --timeout 5 --volumes >/dev/null 2>&1 || true
  fi
  rm -rf "$smoke_root"
}
trap cleanup EXIT INT TERM

PYTHONPATH=backend .venv/bin/python - "$smoke_source" "$smoke_id" <<'PY'
import json
import sys
from pathlib import Path
from app.sandbox import compose_config

source, project_id = Path(sys.argv[1]), sys.argv[2]
spec = compose_config(str(source), project_id)
# Omit `published` so Docker assigns a collision-free loopback port.
spec['services']['web']['ports'][0].pop('published', None)
(source / 'compose.json').write_text(json.dumps(spec, indent=2))
PY

compose=(docker compose -f "$smoke_source/compose.json")
"${compose[@]}" up -d --wait --wait-timeout 150
preview_address="$("${compose[@]}" port web 5173)"
curl --fail --silent --show-error "http://$preview_address/api/health" | grep -q 'connected'
curl --fail --silent --show-error -H 'content-type: application/json' \
  --data '{"text":"Mac persistence check"}' "http://$preview_address/api/notes" | grep -q 'Mac persistence check'

"${compose[@]}" down --timeout 5
"${compose[@]}" up -d --wait --wait-timeout 150
preview_address="$("${compose[@]}" port web 5173)"
curl --fail --silent --show-error "http://$preview_address/api/notes" | grep -q 'Mac persistence check'

"${compose[@]}" exec -T db dropdb -U app --if-exists --force foundry_test
"${compose[@]}" exec -T db createdb -U app foundry_test
"${compose[@]}" run --rm --no-deps -e \
  DATABASE_URL=postgresql+psycopg://app:preview-only@db:5432/foundry_test \
  api python /opt/foundry/runtime.py migrate
"${compose[@]}" run --rm --no-deps -e \
  DATABASE_URL=postgresql+psycopg://app:preview-only@db:5432/foundry_test \
  api python -m pytest -q -p no:cacheprovider /app/tests

node scripts/capture-ui.mjs
node scripts/capture-ui.mjs --accounts
if find screenshots/baseline -type f -name '*.png' -print -quit 2>/dev/null | grep -q .; then
  .venv/bin/python scripts/visual-regression.py
fi
echo "Mac smoke test passed: containers, migrations, isolated tests, persistence, and UI captures."
