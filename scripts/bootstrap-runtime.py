"""Create an offline, target-local venv instead of copying .venv between paths."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

if sys.version_info[:2] != (3, 12):
    raise SystemExit('Install Python 3.12 on this Mac. The app does not bundle a Python interpreter.')
root = Path(__file__).resolve().parents[1]
state = Path(os.environ['FOUNDRY_STATE_ROOT']).resolve()
runtime_root = state / 'runtimes'
runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
hashes = json.loads((root / 'wheel-hashes.json').read_text())
for name, digest in hashes.items():
    if Path(name).name != name or not name.endswith('.whl'):
        raise SystemExit('Invalid runtime wheel manifest.')
    wheel = root / 'wheels' / name
    if wheel.is_symlink() or hashlib.sha256(wheel.read_bytes()).hexdigest() != digest:
        raise SystemExit('Bundled runtime integrity check failed. Rebuild or replace the app.')
fingerprint = hashlib.sha256((json.dumps(hashes, sort_keys=True) + (root / 'runtime.lock').read_text()
                              + sys.version + platform.machine()).encode()).hexdigest()[:16]
runtime = runtime_root / ('v0.8-' + fingerprint)
with (runtime_root / 'bootstrap.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    if not (runtime / 'ready').exists():
        if runtime.exists():
            import uuid
            runtime.rename(runtime.with_name(runtime.name + '-interrupted-' + uuid.uuid4().hex[:8]))
        subprocess.run([sys.executable, '-m', 'venv', str(runtime)], check=True, stdout=sys.stderr)
        subprocess.run([str(runtime / 'bin/python'), '-m', 'pip', 'install', '--no-index',
                        '--find-links', str(root / 'wheels'), '-r', str(root / 'runtime.lock')], check=True, stdout=sys.stderr)
        (runtime / 'ready').write_text(fingerprint)
    subprocess.run([str(runtime / 'bin/python'), '-c', 'import fastapi, psycopg, cryptography, dotenv'],
                   check=True, stdout=sys.stderr)
print(runtime / 'bin/python')
