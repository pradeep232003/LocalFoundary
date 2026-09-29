#!/usr/bin/env python3
"""Windows launcher backend. Runs inside WSL2; installs never copy private data."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SOURCE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOURCE / 'backend'))
from app.host import details, windows_filesystem

CODE_DIRS = ('backend', 'frontend', 'template', 'kits', 'browser', 'protected', 'mobile',
             'release-template', 'scripts', 'tests', 'screenshots')
CODE_FILES = ('.env.example', '.gitignore', '.gitattributes', 'README.md', 'WINDOWS.md', 'MOBILE.md', 'ruff.toml',
              'Windows.ps1', 'CHANGELOG.md', 'VALIDATION.md', 'PROVIDER-ACCEPTANCE.md')
SKIP = {'.git', '.env', '.venv', '.data', 'node_modules', 'dist', '__pycache__',
        '.pytest_cache', 'pytest-of-root', 'acceptance-results', '.DS_Store'}


def private_json(path, value):
    temporary = path.with_name(path.name + '.new')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)
    os.replace(temporary, path)


def environment(install_root, offline=False):
    state = install_root / 'state'
    env = dict(os.environ)
    # Use this installation's settings, even if called from another builder shell.
    for name in ('BUILDER_PORT', 'BUILDER_TOKEN', 'DATABASE_URL', 'OFFLINE_ONLY'):
        env.pop(name, None)
    env.update(FOUNDRY_STATE_ROOT=str(state), FOUNDRY_CONFIG=str(state / '.env'),
               FOUNDRY_DATA=str(state / 'data'), FOUNDRY_OPEN_BROWSER='false',
               FOUNDRY_PYTHON_EXECUTABLE=str(install_root / 'current/.venv/bin/python'))
    tools = state / 'tools.json'
    if tools.exists():
        env['PATH'] = json.loads(tools.read_text())['node_bin'] + os.pathsep + env.get('PATH', '')
    if offline:
        env['OFFLINE_ONLY'] = 'true'
    return env


def identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return {'pid': pid, 'ticks': fields[19],
                'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, IndexError):
        return None


def running(install_root):
    try:
        record = json.loads((install_root / 'state/process.json').read_text())
        return record if identity(record['pid']) == {k: record[k] for k in ('pid', 'ticks', 'boot')} else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


@contextmanager
def management_lock(install_root):
    install_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(install_root, 0o700)
    with (install_root / '.management.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another install/start/stop operation is running. Wait for it to finish.') from None
        yield


def copy_code(source, target):
    source = source.resolve()
    if not (source / 'backend/app/main.py').is_file() or not (source / 'frontend/package-lock.json').is_file():
        raise ValueError('Select the extracted Local Foundry folder containing Windows.ps1.')
    target.mkdir(parents=True, mode=0o700)
    def ignore(folder, names):
        return [n for n in names if n in SKIP or (Path(folder) / n).is_symlink()
                or n.endswith(('.pyc', '.lfr', '.partial'))]
    for name in CODE_DIRS:
        folder = source / name
        if folder.is_symlink():
            raise ValueError('Installation source contains a linked code directory: ' + name)
        shutil.copytree(folder, target / name, ignore=ignore)
    for name in CODE_FILES:
        if (source / name).is_symlink():
            raise ValueError('Installation source contains a linked file: ' + name)
        shutil.copyfile(source / name, target / name)
    # Git/Windows extraction may have changed line endings or executable bits.
    for path in target.rglob('*.sh'):
        path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
        path.chmod(0o755)


def require_wsl():
    if not details()['wsl2']:
        raise ValueError('Use Windows 11 with WSL2 Ubuntu. WSL1 and native Windows Python are unsupported.')


def install(source, install_root):
    if sys.version_info[:2] != (3, 12):
        raise ValueError('Use Ubuntu 24.04 with Python 3.12. See WINDOWS.md.')
    if running(install_root):
        raise ValueError('Stop Local Foundry before upgrading: .\\Windows.ps1 Stop')
    if windows_filesystem(install_root):
        raise ValueError('Install into the WSL Linux filesystem, not a Windows-mounted drive.')
    if not shutil.which('git') or not shutil.which('docker'):
        raise ValueError('Install Git inside Ubuntu and enable Docker Desktop WSL integration. See WINDOWS.md.')
    subprocess.run(['docker', 'info'], check=True, stdout=subprocess.DEVNULL, timeout=30)
    subprocess.run(['docker', 'compose', 'version'], check=True, timeout=15)
    # Detect Ubuntu's separately packaged ensurepip before downloading anything.
    try:
        import ensurepip  # noqa: F401
    except ImportError:
        raise ValueError('In Ubuntu run: sudo apt-get install python3.12-venv git ca-certificates') from None
    from node_runtime import ensure_node
    node_bin = ensure_node(install_root)
    state = install_root / 'state'
    state.mkdir(mode=0o700, exist_ok=True)
    private_json(state / 'tools.json', {'node_bin': str(node_bin)})
    if not (state / '.env').exists():
        # Offline is the default for new Windows workspaces, not for existing users.
        settings = (source / '.env.example').read_text().replace('OFFLINE_ONLY=false', 'OFFLINE_ONLY=true')
        (state / '.env').write_text(settings)
        (state / '.env').chmod(0o600)
    version = json.loads((source / 'frontend/package.json').read_text())['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid release version.')
    release = install_root / 'releases' / (version + '-' + secrets.token_hex(6))
    try:
        copy_code(source, release)
        env = environment(install_root)
        env['FOUNDRY_PYTHON'] = sys.executable
        # Build the venv at its final path: moving a venv breaks its launchers.
        subprocess.run(['bash', str(release / 'scripts/setup.sh')], env=env, cwd=release, check=True)
        subprocess.run([str(node_bin / 'npm'), '--prefix', str(release / 'template/frontend'),
                        'ci', '--no-audit', '--no-fund'], env=env, check=True)
        (release / '.installed').write_text(version + '\n')
        next_link = install_root / '.current-next'
        next_link.unlink(missing_ok=True)
        next_link.symlink_to(release.relative_to(install_root), target_is_directory=True)
        os.replace(next_link, install_root / 'current')
    except BaseException:
        if release.exists() and (install_root / 'current').resolve() != release.resolve():
            shutil.rmtree(release)
        raise
    print('Installed Local Foundry ' + version + '. Existing settings, projects and Docker volumes were preserved.')
    print('Next: .\\Windows.ps1 Start    |    Setup: WINDOWS.md')


def settings(install_root):
    from dotenv import dotenv_values
    values = dotenv_values(install_root / 'state/.env')
    port = int(values.get('BUILDER_PORT', '8765'))
    token = values.get('BUILDER_TOKEN', '')
    if not 1024 <= port <= 65535 or not re.fullmatch(r'[A-Za-z0-9_-]{32,200}', token):
        raise ValueError('Invalid private launcher settings. Rerun Install or inspect the WSL .env file.')
    return port, token


def probe(port, token, timeout=2):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/api/config',
                                     headers={'Authorization': 'Bearer ' + token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        data = json.load(response)
    if not isinstance(data.get('providers'), dict) or not data.get('version'):
        raise ValueError('Unexpected service on the builder port.')
    return data


def launch_result(port, token, status):
    return {'status': status, 'port': port, 'url': f'http://127.0.0.1:{port}/#token={token}'}


def start(install_root, offline=False):
    port, token = settings(install_root)
    record = running(install_root)
    if record:
        data = probe(port, token)
        if offline and not data['offline_only']:
            raise ValueError('The running builder allows network features. Stop it, then Start -Offline.')
        return launch_result(port, token, 'already_running')
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1', port)) == 0:
            raise ValueError(f'Port {port} is already in use. Stop that process or change BUILDER_PORT in the WSL .env.')
    release = (install_root / 'current').resolve()
    log = install_root / 'state/builder.log'
    with os.fdopen(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), 'w') as stream:
        process = subprocess.Popen(['bash', str(release / 'scripts/start.sh')], cwd=release,
                                   env=environment(install_root, offline), stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    record = identity(process.pid)
    if not record:
        raise ValueError('Builder exited immediately. Inspect ' + str(log))
    private_json(install_root / 'state/process.json', record)
    for _ in range(180):
        if process.poll() is not None:
            break
        try:
            data = probe(port, token)
            if offline and not data['offline_only']:
                raise ValueError('Offline mode did not activate.')
            return launch_result(port, token, 'started')
        except (OSError, ValueError, urllib.error.URLError):
            time.sleep(.5)
    # Keep a slow-starting process recorded so Stop can safely clean it up.
    raise ValueError('Builder did not become ready. Run Doctor and inspect ' + str(log))


def stop(install_root, previews=False, database=False):
    record = running(install_root)
    if record:
        # pidfd pins the original process, avoiding PID-reuse races during shutdown.
        descriptor = os.pidfd_open(record['pid'])
        try:
            if identity(record['pid']) == {k: record[k] for k in ('pid', 'ticks', 'boot')}:
                signal.pidfd_send_signal(descriptor, signal.SIGTERM)
                for _ in range(60):
                    if not running(install_root):
                        break
                    time.sleep(.5)
                else:
                    raise ValueError('Builder is still finishing work. Wait and run Stop again; no forced kill was used.')
        finally:
            os.close(descriptor)
    (install_root / 'state/process.json').unlink(missing_ok=True)
    env = environment(install_root)
    if previews:
        subprocess.run(['bash', str(install_root / 'current/scripts/stop-previews.sh')], env=env, check=True)
    if database:
        subprocess.run(['docker', 'compose', '-f', str(install_root / 'state/data/builder-compose.json'),
                        'stop'], env=env, check=True)
    return {'status': 'stopped', 'previews_stopped': previews, 'database_stopped': database,
            'note': 'All database volumes and saved projects are retained.'}


def configure_model(install_root, model, api_base):
    if running(install_root):
        raise ValueError('Stop the builder before changing model settings.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}', model):
        raise ValueError('Use the exact model ID listed by your local server.')
    url = urllib.parse.urlparse(api_base)
    if url.scheme != 'http' or url.hostname not in {'127.0.0.1', '::1'} or url.username or url.password or url.query or url.fragment:
        raise ValueError('Use a literal loopback HTTP endpoint, such as http://127.0.0.1:11434/v1.')
    if url.port is not None and not 1 <= url.port <= 65535:
        raise ValueError('Invalid local model port.')
    from dotenv import set_key
    path = install_root / 'state/.env'
    set_key(path, 'LOCAL_MODEL', model)
    set_key(path, 'LOCAL_API_BASE', api_base.rstrip('/'))
    set_key(path, 'OFFLINE_ONLY', 'true')
    path.chmod(0o600)
    return {'status': 'configured', 'offline_only': True, 'model': model}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'start', 'status', 'stop', 'doctor', 'offline-check', 'paths', 'configure', 'test'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--previews', action='store_true')
    parser.add_argument('--database', action='store_true')
    parser.add_argument('--model', default='')
    parser.add_argument('--api-base', default='http://127.0.0.1:11434/v1')
    args = parser.parse_args()
    require_wsl()
    install_root = Path.home() / '.local/share/local-foundry'
    if windows_filesystem(install_root):
        raise ValueError('Your WSL home must reside on the Linux filesystem. See WINDOWS.md.')
    if args.action != 'install':
        runtime = install_root / 'current/.venv/bin/python'
        if not runtime.exists() or not (install_root / 'current/.installed').exists():
            raise ValueError('Run .\\Windows.ps1 Install first.')
        if Path(sys.prefix).resolve() != (install_root / 'current/.venv').resolve():
            os.execve(runtime, [str(runtime), str(install_root / 'current/scripts/windows/wsl.py'), *sys.argv[1:]],
                      environment(install_root))
    with management_lock(install_root):
        if args.action == 'install':
            if not args.source:
                raise ValueError('Install requires the extracted source folder.')
            install(args.source.resolve(), install_root)
            return 0
        if args.action == 'start':
            result = start(install_root, args.offline)
        elif args.action == 'status':
            port, token = settings(install_root)
            if not running(install_root):
                raise ValueError('Start the builder before checking Windows connectivity.')
            probe(port, token)
            result = launch_result(port, token, 'running')
        elif args.action == 'stop':
            result = stop(install_root, args.previews, args.database)
        elif args.action == 'configure':
            result = configure_model(install_root, args.model, args.api_base)
        elif args.action == 'paths':
            result = {k: str(install_root / v) for k, v in {
                'program': 'current', 'settings': 'state/.env', 'documents': 'state/data/workspace/documents',
                'files': 'state/data/workspace/files', 'log': 'state/builder.log', 'reports': 'state/acceptance-results'}.items()}
        elif args.action in {'doctor', 'offline-check'}:
            from app import diagnostics
            result = diagnostics.report()
            port, token = settings(install_root)
            try:
                actual = probe(port, token)
                result['offline_only'] = actual['offline_only']
                result['checks']['builder_http'] = {'status': 'passed', 'detail': 'Authenticated loopback response'}
            except Exception:
                result['checks']['builder_http'] = {'status': 'failed', 'detail': 'Start the builder, then rerun this check.'}
                result['offline_readiness']['blockers'].append('builder_http')
            result['offline_readiness']['ready'] = not result['offline_readiness']['blockers'] and result['offline_only']
            print(json.dumps(result, indent=2))
            return 0 if args.action == 'doctor' or result['offline_readiness']['ready'] else 2
        elif args.action == 'test':
            return subprocess.run([sys.executable, str(install_root / 'current/scripts/acceptance.py'),
                                   '--mode', 'windows', '--output', str(install_root / 'state/acceptance-results')],
                                  cwd=install_root / 'current', env=environment(install_root)).returncode
        print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print('Local Foundry: ' + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
