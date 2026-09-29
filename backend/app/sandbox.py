import copy
import json
import re
import shutil
from pathlib import Path

from . import config, files
from .process import run, transfer


def validate_id(value):
    if not re.fullmatch(r'[0-9a-f]{32}', value):
        raise ValueError('Invalid project ID.')
    return value


def project_dir(project_id):
    return config.PROJECTS / validate_id(project_id)


def source_dir(project_id):
    return project_dir(project_id) / 'source'


def compose_config(source: Path | str, project_id: str, standalone=False):
    validate_id(project_id)
    source = str(source)
    limits = {'read_only': True, 'cap_drop': ['ALL'],
              'security_opt': ['no-new-privileges:true'], 'pids_limit': 128,
              'mem_limit': '2g', 'cpus': 2, 'init': True,
              'tmpfs': ['/tmp:rw,noexec,nosuid,size=256m'], 'networks': ['app'],
              'logging': {'driver': 'json-file', 'options': {'max-size': '5m', 'max-file': '2'}}}
    def mount(path, dest):
        return {'type': 'bind', 'source': f'{source}/{path}', 'target': dest,
                'read_only': True, 'bind': {'create_host_path': False}}
    web = {**copy.deepcopy(limits), 'image': 'local-foundry-web:2',
           'user': '1000:1000', 'ports': [{'target': 5173, 'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
           'volumes': [mount('frontend/src', '/app/src'), mount('frontend/public', '/app/public')],
           'depends_on': {'api': {'condition': 'service_healthy'}}}
    api = {**copy.deepcopy(limits), 'image': 'local-foundry-api:2', 'user': '1000:1000',
           'environment': {'DATABASE_URL': 'postgresql+psycopg://app:preview-only@db:5432/app',
                           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': '/app',
                           'PYTHONUNBUFFERED': '1'},
           'volumes': [mount('backend/app', '/app/app'), mount('backend/tests', '/app/tests'),
                       mount('backend/migrations', '/app/migrations')],
           'depends_on': {'db': {'condition': 'service_healthy'}},
           'healthcheck': {'test': ['CMD', 'python', '-c',
               "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"],
               'interval': '5s', 'timeout': '4s', 'retries': 15, 'start_period': '10s'}}
    database = {**copy.deepcopy(limits), 'image': 'postgres:17-bookworm', 'user': '999:999',
                'environment': {'POSTGRES_USER': 'app', 'POSTGRES_PASSWORD': 'preview-only',
                                'POSTGRES_DB': 'app'},
                'volumes': ['database:/var/lib/postgresql/data'],
                'tmpfs': ['/tmp:rw,noexec,nosuid,size=128m', '/var/run/postgresql:rw,nosuid,uid=999,gid=999,size=16m'],
                'healthcheck': {'test': ['CMD-SHELL', 'pg_isready -U app -d app'],
                                'interval': '3s', 'timeout': '3s', 'retries': 20}}
    if standalone:
        web['build'] = {'context': './frontend'}
        api['build'] = {'context': './backend'}
        web.pop('image')
        api.pop('image')
        web['ports'][0]['published'] = '5173'
    web['healthcheck'] = {'test': ['CMD', 'node', '-e',
        "fetch('http://127.0.0.1:5173').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"],
        'interval': '3s', 'timeout': '3s', 'retries': 20, 'start_period': '5s'}
    return {'name': ('foundry-export-' if standalone else 'foundry-') + project_id,
            'services': {'web': web, 'api': api, 'db': database},
            'networks': {'app': {'internal': True}}, 'volumes': {'database': {}}}


def seed(project_id, profile='starter'):
    if profile not in {'starter', 'accounts'}:
        raise ValueError('Unknown starter profile.')
    base = project_dir(project_id)
    base.mkdir()
    shutil.copytree(config.ROOT / 'template', base / 'source',
                    ignore=shutil.ignore_patterns('node_modules', 'dist', '__pycache__', '*.pyc'))
    if profile == 'accounts':
        shutil.copytree(config.ROOT / 'kits/accounts', base / 'source', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('node_modules', 'dist', '__pycache__', '*.pyc'))
    files.ensure_layout(base / 'source')
    compose = compose_config('.', project_id, standalone=True)
    if profile == 'accounts':
        compose['services']['api']['environment'].update(APP_ENV='preview', ALLOW_SIGNUP='true',
                                                       PAYMENT_MODE='off', ENABLE_INTEGRATIONS='false')
    (base / 'source/compose.json').write_text(json.dumps(compose, indent=2))
    (base / 'snapshots').mkdir()


def argv(project_id, *args):
    base = project_dir(project_id)
    # Reconstruct trusted config every time, never load model-authored Compose files.
    trusted = base / 'runtime.json'
    temporary = trusted.with_name('runtime-' + __import__('uuid').uuid4().hex + '.tmp')
    spec = compose_config(source_dir(project_id), project_id)
    # Choose a content-addressed, approved runtime; never silently use the base
    # image for a restored project with additional dependencies.
    source = source_dir(project_id)
    from .profiles import get as get_profile
    if get_profile(source) == 'accounts':
        spec['services']['api']['environment'].update(APP_ENV='preview', ALLOW_SIGNUP='true',
                                                    PAYMENT_MODE='off', ENABLE_INTEGRATIONS='false')
    if (source / 'frontend/package.json').is_file() and (source / 'backend/requirements.txt').is_file():
        from .dependencies import image_tags
        for service, image in image_tags(source).items():
            spec['services'][service]['image'] = image
    for service in spec['services'].values():
        service['pull_policy'] = 'never'
    temporary.write_text(json.dumps(spec))
    temporary.replace(trusted)
    return ['docker', 'compose', '-f', str(trusted), '-p', 'foundry-' + project_id, *args]


def command(project_id, *args, timeout=120):
    return run(argv(project_id, *args), timeout=timeout)


def start(project_id):
    files.ensure_layout(source_dir(project_id))
    command(project_id, 'up', '-d', '--wait', '--wait-timeout', '120', timeout=160)
    address = command(project_id, 'port', 'web', '5173').strip()
    if not re.fullmatch(r'127\.0\.0\.1:\d+', address):
        raise RuntimeError('Preview was not bound to loopback.')
    return 'http://' + address


def stop(project_id):
    # Never remove the project's database volume.
    return command(project_id, 'down', '--timeout', '8', timeout=45)


def logs(project_id):
    return command(project_id, 'logs', '--no-color', '--tail', '60', timeout=15)


def execute(project_id, service, shell_command):
    if service not in {'api', 'web'}:
        raise ValueError('Commands can run only in the app or frontend sandbox.')
    if not isinstance(shell_command, str) or not shell_command.strip() or len(shell_command) > 4000:
        raise ValueError('Command must contain 1–4000 characters.')
    # timeout runs INSIDE the container so its process group is also terminated.
    return command(project_id, 'exec', '-T', service, 'timeout', '--kill-after=5', '60',
                   '/bin/sh', '-lc', shell_command, timeout=75)


def check(project_id, service):
    if service == 'web':
        return execute(project_id, 'web', '/app/node_modules/.bin/vite build --configLoader runner --outDir /tmp/foundry-dist')
    if service == 'api':
        prepare_test_database(project_id)
        migrations = test_command(project_id, 'python', '/opt/foundry/runtime.py', 'migrate')
        tests = test_command(project_id, 'python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '/app/tests')
        return migrations + tests
    raise ValueError('Choose web or api.')


def database_ready(project_id):
    files.ensure_layout(source_dir(project_id))
    return command(project_id, 'up', '-d', '--wait', '--wait-timeout', '90', 'db', timeout=110)


def dump_database(project_id, destination):
    database_ready(project_id)
    return transfer(argv(project_id, 'exec', '-T', 'db', 'pg_dump', '-U', 'app', '-d', 'app',
                         '--format=custom', '--no-owner', '--no-privileges'), destination, 'download')


def restore_database(project_id, source):
    database_ready(project_id)
    command(project_id, 'stop', '--timeout', '8', 'web', 'api', timeout=35)
    return transfer(argv(project_id, 'exec', '-T', 'db', 'pg_restore', '-U', 'app', '-d', 'app',
                         '--clean', '--if-exists', '--no-owner', '--no-privileges', '--single-transaction',
                         '--exit-on-error'), source, 'upload')


def apply_migrations(project_id):
    database_ready(project_id)
    return command(project_id, 'run', '--rm', '--no-deps', 'api', 'python', '/opt/foundry/runtime.py',
                   'migrate', timeout=120)


def prepare_test_database(project_id):
    database_ready(project_id)
    command(project_id, 'exec', '-T', 'db', 'dropdb', '-U', 'app', '--if-exists', '--force', 'foundry_test')
    return command(project_id, 'exec', '-T', 'db', 'createdb', '-U', 'app', 'foundry_test')


def test_command(project_id, *args):
    return command(project_id, 'run', '--rm', '--no-deps', '-e',
                   'DATABASE_URL=postgresql+psycopg://app:preview-only@db:5432/foundry_test', 'api', *args, timeout=120)
