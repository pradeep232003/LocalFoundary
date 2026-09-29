"""Trusted security checks and isolated full-stack browser journeys."""
import base64
import json
import secrets
import uuid
from . import config, db, dependencies, files, sandbox, visual
from .process import run


def contracts(project_id):
    root = config.ROOT / 'protected'
    return sandbox.command(project_id, 'run', '--rm', '--no-deps', '-e',
        'DATABASE_URL=postgresql+psycopg://app:preview-only@db:5432/foundry_test',
        '-v', str(root) + ':/opt/foundry/protected:ro', 'api', 'python', '-m', 'pytest',
        '-q', '-p', 'no:cacheprovider', '--confcutdir=/opt/foundry/protected', '/opt/foundry/protected/test_contracts.py', timeout=180)


def check(project_id):
    source = sandbox.source_dir(project_id)
    digest = files.digest(source)
    identifier = uuid.uuid4().hex
    name = 'foundry-journey-' + identifier
    base = sandbox.project_dir(project_id)
    compose_path = base / (name + '.json')
    spec = sandbox.compose_config(source, identifier)
    spec['name'] = name
    spec['services']['web'].pop('ports', None)
    for service, image in dependencies.image_tags(source).items():
        spec['services'][service]['image'] = image
    spec['services']['api']['environment'].update(APP_ENV='preview', ALLOW_SIGNUP='true', PAYMENT_MODE='off', ENABLE_INTEGRATIONS='false')
    for service in spec['services'].values():
        service['pull_policy'] = 'never'
    compose_path.write_text(json.dumps(spec))
    compose = ['docker', 'compose', '-f', str(compose_path), '-p', name]
    credentials = json.dumps({'password': secrets.token_urlsafe(24)})
    protected = str(config.ROOT / 'protected')
    try:
        run([*compose, 'up', '-d', '--wait', '--wait-timeout', '90', 'db'], timeout=110)
        run([*compose, 'run', '--rm', '--no-deps', 'api', 'python', '/opt/foundry/runtime.py', 'migrate'], timeout=120)
        run([*compose, 'run', '--rm', '--no-deps', '-T', '-v', protected + ':/opt/foundry/protected:ro', 'api',
             'python', '/opt/foundry/protected/seed_journeys.py'], input_text=credentials, timeout=60)
        run([*compose, 'up', '-d', '--wait', '--wait-timeout', '120'], timeout=160)
        output = run(['docker', 'run', '--rm', '-i', '--pull=never', '--name', name + '-browser', '--network=' + name + '_app',
            '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true', '--pids-limit=256', '--memory=2g', '--cpus=2',
            '--init', '--shm-size=256m', '--tmpfs=/tmp:rw,nosuid,size=512m', '-v', protected + ':/opt/foundry/protected:ro',
            '--entrypoint=python', visual.IMAGE, '/opt/foundry/protected/journeys.py'], input_text=credentials, timeout=240, output_limit=25_000_000)
        report = json.loads(output)
        for item in report.pop('evidence', []):
            raw = base64.b64decode(item.pop('screenshot'), validate=True)
            if len(raw) > visual.MAX_IMAGE or not raw.startswith(b'\xff\xd8\xff'):
                raise ValueError('Invalid journey screenshot.')
            item.update(id=uuid.uuid4().hex, source_digest=digest, created_at=db.now(), journey=True)
            root = visual.folder(project_id)
            (root / (item['id'] + '.jpg')).write_bytes(raw)
            (root / (item['id'] + '.json')).write_text(json.dumps(item))
        report.update(source_digest=digest, created_at=db.now())
        (base / 'journeys.json').write_text(json.dumps(report))
        if report['status'] != 'passed':
            raise RuntimeError(json.dumps(report)[:3000])
        return report
    finally:
        try:
            run(['docker', 'rm', '--force', name + '-browser'], timeout=15, output_limit=1000)
        except (OSError, RuntimeError):
            pass
        try:
            run([*compose, 'down', '--volumes', '--timeout', '3'], timeout=45, output_limit=1000)
        finally:
            compose_path.unlink(missing_ok=True)


def latest(project_id):
    path = sandbox.project_dir(project_id) / 'journeys.json'
    return json.loads(path.read_text()) if path.is_file() and not path.is_symlink() else None
