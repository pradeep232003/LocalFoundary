"""Exercise WSL launcher invariants on Linux; not native Windows acceptance."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
from types import SimpleNamespace

from dotenv import dotenv_values
import pytest

from app import config, host


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, config.ROOT / 'scripts/windows' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def manager():
    return load('foundry_wsl', 'wsl.py')


@pytest.fixture
def node():
    return load('foundry_node', 'node_runtime.py')


def source_fixture(manager, path):
    for name in manager.CODE_DIRS:
        (path / name).mkdir(parents=True)
    for name in manager.CODE_FILES:
        (path / name).write_text('fixture\n')
    (path / 'backend/app').mkdir()
    (path / 'backend/app/main.py').write_text('# app\n')
    (path / 'frontend/package-lock.json').write_text('{}')
    (path / 'frontend/package.json').write_text('{"version":"0.10.1"}')
    (path / '.env.example').write_text('OFFLINE_ONLY=false\n')
    (path / 'scripts/setup.sh').write_bytes(b'#!/bin/bash\r\nprintf ok\r\n')
    return path


def state_fixture(manager, path):
    (path / 'state').mkdir(parents=True)
    (path / 'state/.env').write_text('BUILDER_TOKEN=' + 'a' * 40 + '\nBUILDER_PORT=8765\nOFFLINE_ONLY=false\n')
    (path / 'current').mkdir()
    return path


def test_windows_mount_detection_handles_custom_paths_and_nested_linux_mounts():
    mounts = ('1 0 0:1 / / rw - ext4 /dev/root rw\n'
              '2 1 0:2 / /shared\\040files rw - 9p C: rw\n'
              '3 2 0:3 / /shared\\040files/linux rw - ext4 /dev/loop rw\n')
    assert host.windows_filesystem('/shared files/projects', mounts)
    assert not host.windows_filesystem('/shared files/linux/projects', mounts)
    assert not host.windows_filesystem('/home/alex/projects', mounts)


@pytest.mark.parametrize('release,expected', [('6.6-microsoft-standard-WSL2', True), ('4.4-Microsoft', False), ('6.8-generic', False)])
def test_host_identifies_wsl2(monkeypatch, release, expected):
    monkeypatch.setattr(host.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(host.platform, 'release', lambda: release)
    assert host.details()['wsl2'] is expected


def test_install_copy_preserves_paths_and_excludes_private_files(manager, tmp_path):
    source = source_fixture(manager, tmp_path / "Downloads' folder with spaces")
    (source / '.env').write_text('private credentials')
    (source / '.data').mkdir()
    (source / '.data/private.txt').write_text('private data')
    (source / 'frontend/node_modules').mkdir()
    (source / 'frontend/node_modules/private.txt').write_text('not source')
    (source / 'backend/leak').symlink_to(source / '.env')
    target = tmp_path / 'Linux home/release'
    manager.copy_code(source, target)
    assert not (target / '.env').exists()
    assert not (target / '.data').exists()
    assert not (target / 'backend/leak').exists()
    assert not (target / 'frontend/node_modules').exists()
    assert b'\r' not in (target / 'scripts/setup.sh').read_bytes()
    assert (target / 'scripts/setup.sh').stat().st_mode & 0o111
    assert (source / '.env').read_text() == 'private credentials'


def test_install_rejects_linked_top_level_code(manager, tmp_path):
    source = source_fixture(manager, tmp_path / 'source')
    (source / 'protected').rmdir()
    (source / 'protected').symlink_to(source / 'backend', target_is_directory=True)
    with pytest.raises(ValueError, match='linked code'):
        manager.copy_code(source, tmp_path / 'target')


def fake_setup(monkeypatch, manager, node, root, fail=False):
    monkeypatch.setitem(sys.modules, 'node_runtime', node)
    monkeypatch.setattr(node, 'ensure_node', lambda _: Path('/usr/bin'))
    monkeypatch.setattr(manager.shutil, 'which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr(manager, 'windows_filesystem', lambda _: False)
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0] == 'bash':
            assert kwargs['env']['FOUNDRY_DATA'] == str(root / 'state/data')
            if fail:
                raise subprocess.CalledProcessError(1, argv)
            (Path(kwargs['cwd']) / '.venv').mkdir()
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(manager.subprocess, 'run', run)
    return calls


@pytest.mark.parametrize('fail', [False, True])
def test_upgrade_activation_and_state_preservation(manager, node, monkeypatch, tmp_path, fail):
    source = source_fixture(manager, tmp_path / 'source')
    root = tmp_path / 'install'
    old = root / 'releases/old'
    old.mkdir(parents=True)
    (root / 'current').symlink_to('releases/old', target_is_directory=True)
    (root / 'state/data').mkdir(parents=True)
    (root / 'state/data/project.txt').write_text('irreplaceable')
    env = root / 'state/.env'
    env.write_text('OFFLINE_ONLY=false\nBUILDER_TOKEN=original\n')
    calls = fake_setup(monkeypatch, manager, node, root, fail)
    if fail:
        with pytest.raises(subprocess.CalledProcessError):
            manager.install(source, root)
        assert (root / 'current').resolve() == old
        assert list((root / 'releases').iterdir()) == [old]
    else:
        manager.install(source, root)
        assert (root / 'current').resolve() != old
        assert (root / 'current/.installed').read_text().strip() == '0.10.1'
        assert old.exists()
        assert (root / 'current/.venv').is_dir()
    assert env.read_text() == 'OFFLINE_ONLY=false\nBUILDER_TOKEN=original\n'
    assert (root / 'state/data/project.txt').read_text() == 'irreplaceable'
    assert all('--volumes' not in argv for argv, _ in calls)


def test_fresh_install_defaults_offline(manager, node, monkeypatch, tmp_path):
    source = source_fixture(manager, tmp_path / 'source')
    root = tmp_path / 'install'
    root.mkdir()
    fake_setup(monkeypatch, manager, node, root)
    manager.install(source, root)
    assert dotenv_values(root / 'state/.env')['OFFLINE_ONLY'] == 'true'
    assert (root / 'state/.env').stat().st_mode & 0o777 == 0o600


def test_parallel_management_is_rejected(manager, tmp_path):
    with manager.management_lock(tmp_path):
        with pytest.raises(ValueError, match='Another install'):
            with manager.management_lock(tmp_path):
                pytest.fail('The second writer acquired the lock')


def test_stale_process_record_does_not_signal_someone_else(manager, monkeypatch, tmp_path):
    root = state_fixture(manager, tmp_path)
    current = {'pid': os.getpid(), 'ticks': '123', 'boot': 'test-boot'}
    monkeypatch.setattr(manager, 'identity', lambda pid: current.copy())
    record = {**current, 'ticks': '124'}
    manager.private_json(root / 'state/process.json', record)
    monkeypatch.setattr(signal, 'pidfd_send_signal', lambda *a: pytest.fail('Signaled a reused PID'))
    assert manager.stop(root)['status'] == 'stopped'
    assert not (root / 'state/process.json').exists()


def test_stop_terminates_only_recorded_process_and_keeps_state(manager, tmp_path):
    root = state_fixture(manager, tmp_path)
    if manager.identity(os.getpid()) is None:
        pytest.skip('Host blocks /proc process identity; run on WSL2 to exercise pidfd protection.')
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        manager.private_json(root / 'state/process.json', manager.identity(child.pid))
        manager.stop(root)
        child.wait(timeout=3)
        assert child.returncode == -signal.SIGTERM
        assert (root / 'state/.env').exists()
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=3)


def test_offline_start_refuses_to_reuse_online_builder(manager, monkeypatch, tmp_path):
    root = state_fixture(manager, tmp_path)
    monkeypatch.setattr(manager, 'running', lambda _: {'pid': 123})
    monkeypatch.setattr(manager, 'probe', lambda *a: {'offline_only': False})
    with pytest.raises(ValueError, match='Stop it'):
        manager.start(root, offline=True)


def test_offline_start_passes_state_and_never_calls_installer(manager, monkeypatch, tmp_path):
    root = state_fixture(manager, tmp_path / "home with ' spaces")
    monkeypatch.setattr(manager, 'running', lambda _: None)
    monkeypatch.setattr(manager, 'identity', lambda _: {'pid':123, 'ticks':'1', 'boot':'test'})
    class FreePort:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def connect_ex(self, address): return 1
    monkeypatch.setattr(manager.socket, 'socket', lambda: FreePort())
    commands = []
    def spawn(argv, **kwargs):
        commands.append(argv)
        assert kwargs['env']['OFFLINE_ONLY'] == 'true'
        assert kwargs['env']['FOUNDRY_OPEN_BROWSER'] == 'false'
        assert kwargs['env']['FOUNDRY_DATA'] == str(root / 'state/data')
        assert kwargs['start_new_session'] is True
        return SimpleNamespace(pid=123, poll=lambda: None)
    monkeypatch.setattr(manager.subprocess, 'Popen', spawn)
    monkeypatch.setattr(manager, 'probe', lambda *a: {'offline_only':True})
    result = manager.start(root, offline=True)
    assert result['url'].endswith('#token=' + 'a'*40)
    assert commands == [['bash', str(root / 'current/scripts/start.sh')]]
    assert (root / 'state/builder.log').stat().st_mode & 0o777 == 0o600
    assert (root / 'state/process.json').stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('endpoint', ['http://192.168.1.2:11434/v1', 'https://127.0.0.1/v1', 'http://localhost:11434/v1', 'http://secret@127.0.0.1/v1'])
def test_model_configuration_keeps_loopback_boundary(manager, tmp_path, endpoint):
    root = state_fixture(manager, tmp_path)
    original = (root / 'state/.env').read_text()
    with pytest.raises(ValueError, match='loopback'):
        manager.configure_model(root, 'test-coder:7b', endpoint)
    assert (root / 'state/.env').read_text() == original


def test_model_configuration_preserves_token(manager, tmp_path):
    root = state_fixture(manager, tmp_path)
    manager.configure_model(root, 'vendor/test-coder:7b', 'http://127.0.0.1:11434/v1')
    values = dotenv_values(root / 'state/.env')
    assert values['BUILDER_TOKEN'] == 'a'*40
    assert values['LOCAL_MODEL'] == 'vendor/test-coder:7b'
    assert values['OFFLINE_ONLY'] == 'true'


@pytest.mark.parametrize('unsafe', ['../escape', '/absolute', 'node-test/../../escape'])
def test_node_archive_rejects_escaping_paths(node, tmp_path, unsafe):
    archive = tmp_path / 'node.tar.xz'
    with tarfile.open(archive, 'w:xz') as tar:
        entry = tarfile.TarInfo(unsafe)
        entry.size = 1
        tar.addfile(entry, io.BytesIO(b'x'))
    with pytest.raises(ValueError, match='Unsafe path'):
        node.extract_verified(archive, tmp_path / 'output', 'node-test')
    assert not (tmp_path / 'escape').exists()


def test_node_archive_rejects_link_escape(node, tmp_path):
    archive = tmp_path / 'node.tar.xz'
    with tarfile.open(archive, 'w:xz') as tar:
        entry = tarfile.TarInfo('node-test/link')
        entry.type = tarfile.SYMTYPE
        entry.linkname = '../../escape'
        tar.addfile(entry)
    with pytest.raises(tarfile.FilterError):
        node.extract_verified(archive, tmp_path / 'output', 'node-test')


def test_node_download_checksum_failure_never_extracts(node, monkeypatch, tmp_path):
    monkeypatch.setattr(node, 'supported_node', lambda _: False)
    monkeypatch.setattr(node.shutil, 'which', lambda _: None)
    monkeypatch.setattr(node.platform, 'machine', lambda: 'x86_64')
    def fetch(url, limit):
        if url.endswith('/index.json'):
            return json.dumps([{'version':'v24.0.0', 'lts':'test', 'files':['linux-x64']}]).encode()
        if url.endswith('/SHASUMS256.txt'):
            return (hashlib.sha256(b'good').hexdigest() + '  node-v24.0.0-linux-x64.tar.xz\n').encode()
        return b'corrupted'
    monkeypatch.setattr(node, 'fetch', fetch)
    monkeypatch.setattr(node, 'extract_verified', lambda *a: pytest.fail('Extracted an unverified archive'))
    with pytest.raises(ValueError, match='checksum mismatch'):
        node.ensure_node(tmp_path)
    assert not (tmp_path / 'tools/node').exists()
