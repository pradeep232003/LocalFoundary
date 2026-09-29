"""Generate unique, local release credentials. Never overwrite existing .env."""
import os
import base64
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
for folder in ('frontend/public', 'backend/migrations'):
    (root / folder).mkdir(parents=True, exist_ok=True)
destination = root / '.env'
try:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print('Existing .env kept. Do not rotate a live database password by editing .env alone.')
else:
    with os.fdopen(descriptor, 'w') as stream:
        stream.write('RELEASE_NAME=foundry-release-' + secrets.token_hex(4) + '\n')
        stream.write('DATABASE_PASSWORD=' + secrets.token_hex(32) + '\nAPP_PORT=8080\n')
        stream.write('APP_ENV=preview\nALLOW_SIGNUP=true\nPAYMENT_MODE=off\nENABLE_INTEGRATIONS=false\n')
        stream.write('APP_ENCRYPTION_KEY=' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode() + '\n')
        stream.write('OPS_TOKEN=' + secrets.token_urlsafe(32) + '\n')
    print('Created private .env. Back it up securely; it is required to recover your deployment.')
