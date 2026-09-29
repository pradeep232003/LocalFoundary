#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Build the macOS application on the target Mac."
  exit 1
fi
if [[ ! -x .venv/bin/python || ! -f frontend/dist/index.html ]]; then
  echo "Run ./scripts/setup.sh before packaging the app."
  exit 1
fi
docker info >/dev/null
accounts_image="$(.venv/bin/python scripts/cache-accounts.py --print-image)"
for image in local-foundry-web:2 local-foundry-api:2 local-foundry-browser:4 postgres:17-bookworm "$accounts_image"; do
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "Missing $image. Run ./scripts/setup.sh while connected, then package again."
    exit 1
  fi
done
release_root="$PWD/release"
app="$release_root/Local Foundry.app"
contents="$app/Contents"
resources="$contents/Resources/local-foundry"
mkdir -p "$release_root"
if [[ -e "$app" ]]; then
  previous_app="$(mktemp -d "$release_root/previous-app.XXXXXX")"
  mv "$app" "$previous_app/"
  echo "Previous app preserved in $previous_app"
fi
mkdir -p "$contents/MacOS" "$resources/frontend"
for directory in backend template kits scripts browser protected mobile release-template; do
  ditto "$directory" "$resources/$directory"
done
ditto frontend/dist "$resources/frontend/dist"
cp .env.example README.md MOBILE.md VALIDATION.md "$resources/"
find "$resources" -type d \( -name node_modules -o -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
find "$resources" -type f \( -name '*.pyc' -o -name '.DS_Store' \) -delete
echo "Downloading binary Python wheels for this Mac. No virtual environment will be copied."
.venv/bin/python scripts/package-runtime.py "$resources"
docker save --output "$resources/docker-images.tar" \
  local-foundry-web:2 local-foundry-api:2 local-foundry-browser:4 postgres:17-bookworm "$accounts_image"
cp scripts/macos/launcher.sh "$contents/MacOS/local-foundry"
cp scripts/macos/Info.plist "$contents/Info.plist"
chmod 755 "$contents/MacOS/local-foundry" "$resources/scripts/start.sh"
sign_identity="${APPLE_SIGN_IDENTITY:--}"
codesign --force --deep --options runtime --sign "$sign_identity" "$app"
if [[ -n "${APPLE_NOTARY_PROFILE:-}" ]]; then
  archive="$release_root/Local-Foundry-notarization.zip"
  ditto -c -k --keepParent "$app" "$archive"
  xcrun notarytool submit "$archive" --keychain-profile "$APPLE_NOTARY_PROFILE" --wait
  xcrun stapler staple "$app"
fi
echo "Created $app. Python 3.12 and Docker Desktop are required on the target Mac."
