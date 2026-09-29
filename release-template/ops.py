"""Single-host release operations. Run from an Accounts release on the deployment host."""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parent
STATE = ROOT / '.ops'
SCHEMA_SQL = "SELECT COALESCE(json_object_agg(name,sha256),'{}'::json) FROM _foundry_migrations"


def command(args, timeout=180):
    result = subprocess.run(args, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Operation failed: ' + Path(args[0]).name + '. Inspect container status; credential-bearing output was withheld.')
    return result.stdout.decode().strip()


def write_json(path, value):
    temp = path.with_suffix('.partial')
    with open(temp, 'w') as stream:
        os.chmod(temp, 0o600)
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def environment(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('Run configure-release.py first; use a regular private environment file.')
    values = dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line and not line.startswith('#'))
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,60}', values.get('RELEASE_NAME', '')):
        raise ValueError('Invalid release name')
    return values


def compose(stage=False, images=None):
    env = ROOT / ('.env.stage' if stage else '.env')
    values = environment(env)
    args = ['docker', 'compose', '--env-file', str(env), '-p', values['RELEASE_NAME'] + ('-stage' if stage else ''), '-f', str(ROOT / 'compose.yaml')]
    if not stage:
        for name in ('public', 'online', 'monitoring'):
            if name in read_json(STATE / 'overlays.json', []):
                args += ['-f', str(ROOT / ('compose.' + name + '.yaml'))]
    if images:
        override = STATE / ('stage-images.json' if stage else 'images.json')
        write_json(override, {'services': {k: {'image': v} for k, v in images.items()}})
        args += ['-f', str(override)]
    return args


def candidate():
    release = read_json(ROOT / 'release.json')
    if release.get('profile') != 'accounts' or not release.get('release_id'):
        raise ValueError('Lifecycle operations require the Accounts security/journey gate (v0.6+) in this release.')
    name = environment(ROOT / '.env')['RELEASE_NAME']
    images = {}
    for service in ('web', 'api', 'egress'):
        tag = name + '-' + service + ':' + release['release_id'][:24]
        images[service] = command(['docker', 'image', 'inspect', '--format={{.Id}}', tag])
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', images[service]):
            raise ValueError('Build the release images first.')
    images.update(migrate=images['api'], worker=images['api'])
    migrations = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'backend/migrations').glob('*.sql'))}
    if migrations != release['migrations']:
        raise ValueError('Release migrations changed after export. Revalidate and export again.')
    return {'release_id': release['release_id'], 'images': images, 'migrations': migrations}


def active_images(data):
    # Egress belongs only to the explicit online overlay.
    return {k: v for k, v in data['images'].items() if k != 'egress' or 'online' in read_json(STATE/'overlays.json', [])}


def pipeline(first, second, key, source=None, destination=None):
    """Two child processes, bounded transfer; never log binary dumps or keys."""
    children = []
    errors = []
    try:
        if source is None:
            producer = subprocess.Popen(first, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            children.append(producer)
            input_stream = producer.stdout
            crypto = subprocess.Popen(second, cwd=ROOT, stdin=subprocess.PIPE, stdout=destination, stderr=subprocess.DEVNULL)
            children.append(crypto)
        else:
            crypto = subprocess.Popen(first, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            children.append(crypto)
            consumer = subprocess.Popen(second, cwd=ROOT, stdin=crypto.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(consumer)
            crypto.stdout.close()
            input_stream = source
        def feed():
            try:
                crypto.stdin.write(key)
                shutil.copyfileobj(input_stream, crypto.stdin, 1024 * 1024)
                crypto.stdin.close()
            except (OSError, ValueError) as exc:
                errors.append(type(exc).__name__)
        thread = threading.Thread(target=feed, daemon=True)
        thread.start()
        deadline = time.monotonic() + 240
        for child in children:
            if child.wait(timeout=max(1, deadline-time.monotonic())):
                raise RuntimeError('Backup/restore pipeline failed. The incomplete output was rejected.')
        thread.join(timeout=2)
        if thread.is_alive() or errors:
            raise RuntimeError('Incomplete backup/restore transfer')
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()


def crypto_args(image, mode, name):
    return ['docker', 'run', '--rm', '-i', '--pull=never', '--name', name, '--network=none', '--read-only', '--user=1000:1000',
            '--cap-drop=ALL', '--security-opt=no-new-privileges:true', '--pids-limit=64', '--memory=1g', '--cpus=1',
            '--tmpfs=/tmp:rw,noexec,nosuid,size=600m', '-v', str(ROOT/'ops/crypto_stream.py')+':/crypto.py:ro',
            '--entrypoint=python', image, '/crypto.py', mode]


def key_bytes(create=True):
    path = STATE / 'backup.key'
    if not path.exists():
        if not create or list((STATE/'backups').glob('*.lfb')):
            raise ValueError('Backup key is missing. Recover the original key; existing backups cannot use a new one.')
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(secrets.token_bytes(32))
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError('Backup key must be a private regular file.')
    key = path.read_bytes()
    if len(key) != 32:
        raise ValueError('Invalid backup key; do not replace a key needed for existing backups.')
    return key


def backup(image):
    folder = STATE / 'backups'
    folder.mkdir(exist_ok=True, mode=0o700)
    name = 'backup-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(4)
    partial = folder / (name + '.partial')
    destination = folder / (name + '.lfb')
    crypto = 'foundry-encrypt-' + uuid.uuid4().hex
    try:
        with partial.open('xb') as stream:
            os.chmod(partial, 0o600)
            pipeline([*compose(), 'exec', '-T', 'db', 'pg_dump', '-U', 'app', '-d', 'app', '--format=custom', '--no-owner', '--no-privileges', '--lock-wait-timeout=15000'],
                     crypto_args(image, 'encrypt', crypto), key_bytes(), destination=stream)
            stream.flush()
            os.fsync(stream.fileno())
        partial.replace(destination)
        write_json(destination.with_suffix('.json'), {'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'created_at': time.time(), 'image': image, 'restored': False})
        return destination
    finally:
        partial.unlink(missing_ok=True)
        subprocess.run(['docker', 'rm', '-f', crypto], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def drill(path, image):
    path = path.resolve(strict=True)
    if path.parent != (STATE/'backups').resolve() or path.suffix != '.lfb':
        raise ValueError('Select an encrypted backup from this deployment.')
    metadata = read_json(path.with_suffix('.json'))
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata['sha256']:
        raise ValueError('Backup checksum mismatch')
    identifier = uuid.uuid4().hex
    database, crypto = 'foundry-drill-'+identifier, 'foundry-decrypt-'+identifier
    started = time.monotonic()
    try:
        command(['docker', 'run', '-d', '--pull=never', '--name', database, '--network=none', '--read-only', '--user=999:999',
            '--cap-drop=ALL', '--security-opt=no-new-privileges:true', '--memory=2g', '--pids-limit=128',
            '--tmpfs=/var/lib/postgresql/data:rw,uid=999,gid=999,size=1g', '--tmpfs=/var/run/postgresql:rw,uid=999,gid=999,size=16m',
            '--tmpfs=/tmp:rw,noexec,nosuid,size=32m', '-e', 'POSTGRES_USER=app', '-e', 'POSTGRES_DB=app',
            '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:17-bookworm'])
        for attempt in range(30):
            try:
                command(['docker', 'exec', database, 'pg_isready', '-U', 'app', '-d', 'app'], timeout=5)
                break
            except RuntimeError:
                time.sleep(1)
        else:
            raise RuntimeError('Restore drill database did not become ready')
        with path.open('rb') as stream:
            pipeline(crypto_args(image, 'decrypt', crypto), ['docker', 'exec', '-i', database, 'pg_restore', '-U', 'app', '-d', 'app',
                     '--no-owner', '--no-privileges', '--single-transaction', '--exit-on-error'], key_bytes(create=False), source=stream)
        count = command(['docker', 'exec', database, 'psql', '-U', 'app', '-d', 'app', '-Atc',
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"])
        metadata.update(restored=True, restored_at=time.time(), restore_seconds=round(time.monotonic()-started, 2), tables=int(count))
        write_json(path.with_suffix('.json'), metadata)
        return metadata
    finally:
        subprocess.run(['docker', 'rm', '-f', database, crypto], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


def schema():
    return json.loads(command([*compose(), 'exec', '-T', 'db', 'psql', '-U', 'app', '-d', 'app', '-Atc', SCHEMA_SQL]))


def compatible(previous, actual):
    return bool(previous) and previous.get('migrations') == actual


def stage(data):
    path = ROOT / '.env.stage'
    if not path.exists():
        name = environment(ROOT/'.env')['RELEASE_NAME']
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
            stream.write('RELEASE_NAME='+name+'\nDATABASE_PASSWORD='+secrets.token_hex(32)+'\nAPP_PORT=8081\nAPP_ENV=preview\nALLOW_SIGNUP=true\nPAYMENT_MODE=off\nENABLE_INTEGRATIONS=false\nAPP_ENCRYPTION_KEY='+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()+'\nOPS_TOKEN='+secrets.token_urlsafe(32)+'\n')
    settings = environment(path)
    if any(settings.get(k) != v for k, v in {'APP_ENV':'preview', 'PAYMENT_MODE':'off', 'ENABLE_INTEGRATIONS':'false'}.items()):
        raise ValueError('Staging must use isolated preview settings.')
    images = {k: v for k, v in data['images'].items() if k != 'egress'}
    command([*compose(True, images), 'up', '-d', '--no-build', '--wait', '--wait-timeout', '150'], timeout=190)
    write_json(STATE/'staged.json', {**data, 'checked_at': time.time()})


def deploy(data):
    staged = read_json(STATE/'staged.json', {})
    if any(staged.get(k) != data[k] for k in ('release_id', 'images', 'migrations')) or time.time()-staged.get('checked_at', 0) > 86400:
        raise ValueError('Stage these exact images successfully within 24 hours before deployment.')
    state = read_json(STATE/'state.json', {})
    command([*compose(), 'up', '-d', '--no-build', '--wait', 'db'])
    path = backup(data['images']['api'])
    drill(path, data['images']['api'])
    state.update(pending=data, pre_deploy_backup=path.name, phase='deploying')
    write_json(STATE/'state.json', state)
    try:
        command([*compose(False, active_images(data)), 'up', '-d', '--no-build', '--wait', '--wait-timeout', '150'], timeout=190)
        if schema() != data['migrations']:
            raise RuntimeError('Deployment migration ledger does not match the release.')
    except Exception:
        state['phase'] = 'failed_needs_review'
        write_json(STATE/'state.json', state)
        raise
    write_json(STATE/'state.json', {'current': data, 'previous': state.get('current'), 'phase': 'healthy', 'deployed_at': time.time(), 'pre_deploy_backup': path.name})


def rollback():
    state = read_json(STATE/'state.json', {})
    previous = state.get('current') if state.get('phase') != 'healthy' else state.get('previous')
    if not compatible(previous, schema()):
        raise ValueError('Rollback blocked: database migrations differ. Prepare a forward fix or an explicit data recovery plan.')
    command([*compose(False, active_images(previous)), 'up', '-d', '--no-build', '--wait', '--wait-timeout', '150'], timeout=190)
    write_json(STATE/'state.json', {'current': previous, 'previous': state.get('current'), 'phase': 'healthy', 'rolled_back_at': time.time()})


def schedule():
    program = [sys.executable, str(ROOT/'ops.py'), 'backup']
    if sys.platform == 'darwin':
        path = STATE/'local-foundry.backup.plist'
        path.write_bytes(plistlib.dumps({'Label': 'local-foundry.backup.'+environment(ROOT/'.env')['RELEASE_NAME'], 'ProgramArguments': program,
            'StartCalendarInterval': {'Hour':3, 'Minute':15}, 'WorkingDirectory':str(ROOT),
            'EnvironmentVariables': {'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')},
            'StandardOutPath':str(STATE/'backup.log'), 'StandardErrorPath':str(STATE/'backup-errors.log')}))
        print('Schedule created:', path, '\nInstall with: launchctl bootstrap gui/$(id -u) ' + shlex.quote(str(path)))
    else:
        path = STATE/'backup.cron'
        path.write_text('PATH='+os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin')+'\n15 3 * * * '+shlex.join(program)+' >> '+shlex.quote(str(STATE/'backup.log'))+' 2>&1\n')
        print('Schedule created:', path, '\nAdd its entry to the deployment user crontab; preserve existing entries.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage','deploy','rollback','backup','restore-drill','schedule','status'])
    parser.add_argument('--backup', help='Encrypted backup filename for restore-drill')
    parser.add_argument('--overlays', help='Persist explicit production overlays: public,online,monitoring (or none)')
    args = parser.parse_args()
    os.umask(0o077)
    STATE.mkdir(mode=0o700, exist_ok=True)
    if STATE.is_symlink():
        raise ValueError('Unsafe operations directory')
    with (STATE/'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.overlays is not None:
            names = [] if args.overlays == 'none' else args.overlays.split(',')
            if any(n not in {'public','online','monitoring'} for n in names):
                raise ValueError('Unknown deployment overlay')
            write_json(STATE/'overlays.json', names)
        if args.action == 'status':
            print(json.dumps(read_json(STATE/'state.json', {'phase':'not_deployed'}), indent=2))
        elif args.action == 'schedule':
            schedule()
        elif args.action == 'rollback':
            rollback()
        else:
            data = candidate()
            if args.action == 'stage':
                stage(data)
            elif args.action == 'deploy':
                deploy(data)
            elif args.action == 'backup':
                path = backup(data['images']['api'])
                print('Encrypted backup and restore drill:', path.name, json.dumps(drill(path, data['images']['api'])))
            else:
                if not args.backup or Path(args.backup).name != args.backup:
                    raise ValueError('Provide --backup with a backup filename')
                print(json.dumps(drill(STATE/'backups'/args.backup, data['images']['api'])))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit(type(exc).__name__ + ': ' + str(exc)) from exc
