"""Cache binary wheels for this Mac's Python 3.12. Run explicitly while connected."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

if sys.version_info[:2] != (3, 12):
    raise SystemExit('Package using the Python 3.12 environment created by setup.sh.')
destination = Path(sys.argv[1]).resolve()
destination.mkdir(parents=True, exist_ok=True)
wheelhouse = destination / 'wheels'
wheelhouse.mkdir(exist_ok=True)
packages = json.loads(subprocess.check_output([sys.executable, '-m', 'pip', 'list', '--format=json'], text=True))
lines = []
for package in packages:
    name, version = package['name'], package['version']
    if not re.fullmatch(r'[A-Za-z0-9._-]+', name) or not re.fullmatch(r'[A-Za-z0-9.+!-]+', version):
        raise SystemExit('Cannot package a non-registry Python dependency.')
    lines.append(name + '==' + version)
(destination / 'runtime.lock').write_text('\n'.join(sorted(lines)) + '\n')
subprocess.run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:', '--dest', str(wheelhouse),
                '-r', str(destination / 'runtime.lock')], check=True)
hashes = {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in wheelhouse.glob('*.whl')}
(destination / 'wheel-hashes.json').write_text(json.dumps(hashes, sort_keys=True, indent=2))
