#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
python3 configure-release.py
python3 - <<'PY'
import hashlib, json, subprocess
from pathlib import Path
release = json.loads(Path('release.json').read_text())
for filename, expected in release['file_hashes'].items():
    path = Path(filename)
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('Release source changed after export. Revalidate and export a new release before building.')
for image in [*release['runtime_images'].values(), 'postgres:17-bookworm']:
    subprocess.run(['docker', 'image', 'inspect', image], check=True, stdout=subprocess.DEVNULL)
settings = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines() if '=' in line)
name = settings['RELEASE_NAME']
tag = release['release_id'][:24]
for service, folder in [('web', 'frontend'), ('api', 'backend')]:
    subprocess.run(['docker', 'build', '--pull=false', '--network=none', '-t', name + '-' + service + ':' + tag, folder], check=True)
if release.get('profile') == 'accounts':
    subprocess.run(['docker', 'build', '--pull=false', '--network=none', '-t', name + '-egress:' + tag, 'egress'], check=True)
path = Path('.env')
lines = [line for line in path.read_text().splitlines() if not line.startswith('RELEASE_TAG=')]
path.write_text('\n'.join(lines) + '\nRELEASE_TAG=' + tag + '\n')
path.chmod(0o600)
PY
echo 'Release images built without network access. Start explicitly with: docker compose up -d --wait'
