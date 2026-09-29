"""Create private local configuration. Does not print credentials."""
import json
import hashlib
import os
import secrets
import socket
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values, set_key

root = Path(__file__).resolve().parents[1]
state_root = Path(os.environ.get('FOUNDRY_STATE_ROOT', root)).expanduser().resolve()
state_root.mkdir(parents=True, exist_ok=True)
env_path = Path(os.environ.get('FOUNDRY_CONFIG', state_root / '.env')).expanduser().resolve()
if not env_path.exists():
    env_path.write_text((root / '.env.example').read_text())
os.chmod(env_path, 0o600)
values = dotenv_values(env_path)
if not values.get('BUILDER_TOKEN'):
    set_key(env_path, 'BUILDER_TOKEN', secrets.token_urlsafe(40))
if not values.get('DATABASE_URL'):
    password = secrets.token_hex(24)
    port = 55432
    if state_root != root:
        # A fresh packaged app gets a separate DB and password. Explicit migration
        # preserves the original URL and Compose project name instead.
        for candidate in range(55433, 55500):
            try:
                with socket.socket() as probe:
                    probe.bind(('127.0.0.1', candidate))
                port = candidate
                break
            except OSError:
                continue
        else:
            raise SystemExit('No loopback database port available. Configure DATABASE_URL explicitly.')
    set_key(env_path, 'DATABASE_URL', f'postgresql://foundry:{password}@127.0.0.1:{port}/foundry')
values = dotenv_values(env_path)
url = urlparse(values['DATABASE_URL'])
if url.hostname != '127.0.0.1' or url.path != '/foundry' or url.username != 'foundry':
    raise SystemExit('The setup script manages a local foundry database. Restore its DATABASE_URL or configure PostgreSQL manually.')
data = Path(os.environ.get('FOUNDRY_DATA', state_root / '.data')).expanduser().resolve()
data.mkdir(exist_ok=True)
os.chmod(data, 0o700)
path = data / 'builder-compose.json'
instance = 'local-foundry-builder' if state_root == root else 'local-foundry-' + hashlib.sha256(str(state_root).encode()).hexdigest()[:10]
if path.exists():
    instance = json.loads(path.read_text())['name']
compose = {'name': instance, 'services': {'db': {
    'image': 'postgres:17-bookworm', 'restart': 'unless-stopped',
    'environment': {'POSTGRES_USER': 'foundry', 'POSTGRES_PASSWORD': url.password, 'POSTGRES_DB': 'foundry'},
    'ports': [f'127.0.0.1:{url.port}:5432'], 'volumes': ['builder-data:/var/lib/postgresql/data'],
    'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U foundry -d foundry'],
                    'interval': '3s', 'timeout': '3s', 'retries': 20}}},
    'volumes': {'builder-data': {}}}
path.write_text(json.dumps(compose, indent=2))
os.chmod(path, 0o600)
