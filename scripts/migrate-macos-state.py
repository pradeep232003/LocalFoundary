"""Explicit, non-destructive source → packaged-app state migration on the SAME Mac."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import tempfile

from dotenv import dotenv_values

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True, help='Existing Local Foundry source folder')
parser.add_argument('--destination', type=Path, default=Path.home() / 'Library/Application Support/Local Foundry')
args = parser.parse_args()
source, destination = args.source.expanduser().resolve(), args.destination.expanduser().resolve()
source_env, source_data = source / '.env', source / '.data'
if not source_env.is_file() or not (source_data / 'builder-compose.json').is_file():
    raise SystemExit('Source must contain .env and .data/builder-compose.json.')
if destination == source or destination.is_relative_to(source):
    raise SystemExit('Destination must be outside the source installation.')
if (destination / '.env').exists() or (destination / 'data').exists():
    raise SystemExit('Destination already has app state. Nothing was overwritten. Keep using that installation or choose an empty destination.')
values = dotenv_values(source_env)
if values.get('FOUNDRY_DATA'):
    raise SystemExit('Custom FOUNDRY_DATA requires an explicit, reviewed migration; this helper only handles .data.')
try:
    with socket.create_connection(('127.0.0.1', int(values.get('BUILDER_PORT') or 8765)), timeout=1):
        raise SystemExit('Stop both builder UIs before migration. PostgreSQL may remain running.')
except OSError:
    pass
if any(path.is_symlink() for path in source_data.rglob('*')):
    raise SystemExit('Source state contains symlinks. Review them before migration.')
destination.mkdir(parents=True, exist_ok=True, mode=0o700)
with tempfile.TemporaryDirectory(prefix='migration-', dir=destination) as temporary:
    staged = Path(temporary)
    shutil.copy2(source_env, staged / '.env')
    os.chmod(staged / '.env', 0o600)
    shutil.copytree(source_data, staged / 'data')
    (staged / 'data').rename(destination / 'data')
    (staged / '.env').rename(destination / '.env')
print('Copied state without deleting the original. The existing Docker database volume and credentials are preserved.')
print('Open the packaged app, reindex documents, and verify projects before retiring the source installation. Do not run both simultaneously.')
