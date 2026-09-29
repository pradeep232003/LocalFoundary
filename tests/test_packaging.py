import json
import plistlib
import runpy
import socket
import sys
from urllib.parse import urlparse

from dotenv import dotenv_values
import pytest

from app import config


class AvailablePort:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def bind(self, address):
        assert address[0] == '127.0.0.1'


def configure(monkeypatch, state):
    monkeypatch.setenv('FOUNDRY_STATE_ROOT', str(state))
    monkeypatch.setenv('FOUNDRY_CONFIG', str(state / '.env'))
    monkeypatch.setenv('FOUNDRY_DATA', str(state / 'data'))
    monkeypatch.setattr(socket, 'socket', lambda *a, **kw: AvailablePort())
    runpy.run_path(str(config.ROOT / 'scripts/configure.py'), run_name='__main__')
    return dotenv_values(state / '.env'), json.loads((state / 'data/builder-compose.json').read_text())


def test_fresh_packaged_state_uses_own_namespace_and_port(tmp_path, monkeypatch):
    env, compose = configure(monkeypatch, tmp_path)
    assert compose['name'].startswith('local-foundry-')
    assert compose['name'] != 'local-foundry-builder'
    assert urlparse(env['DATABASE_URL']).port == 55433
    before = env['DATABASE_URL']
    second, same_compose = configure(monkeypatch, tmp_path)
    assert second['DATABASE_URL'] == before
    assert same_compose['name'] == compose['name']


def test_configure_preserves_migrated_volume_namespace(tmp_path, monkeypatch):
    (tmp_path / 'data').mkdir()
    (tmp_path / '.env').write_text('DATABASE_URL=postgresql://foundry:existing-password@127.0.0.1:55432/foundry\nBUILDER_TOKEN=existing-token\n')
    (tmp_path / 'data/builder-compose.json').write_text(json.dumps({'name': 'local-foundry-builder'}))
    env, compose = configure(monkeypatch, tmp_path)
    assert compose['name'] == 'local-foundry-builder'
    assert urlparse(env['DATABASE_URL']).port == 55432
    assert env['BUILDER_TOKEN'] == 'existing-token'


def test_mac_migration_copies_without_overwriting_or_deleting(tmp_path, monkeypatch):
    source, destination = tmp_path / 'source', tmp_path / 'app-state'
    (source / '.data').mkdir(parents=True)
    (source / '.env').write_text('BUILDER_PORT=8765\nDATABASE_URL=preserve-this\n')
    (source / '.data/builder-compose.json').write_text('{"name":"original-builder"}')
    (source / '.data/project.txt').write_text('keep this source')
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: (_ for _ in ()).throw(OSError('not running')))
    monkeypatch.setattr(sys, 'argv', ['migrate', '--source', str(source), '--destination', str(destination)])
    script = str(config.ROOT / 'scripts/migrate-macos-state.py')
    runpy.run_path(script, run_name='__main__')
    assert (source / '.data/project.txt').read_text() == (destination / 'data/project.txt').read_text()
    assert (source / '.env').read_text() == (destination / '.env').read_text()
    with pytest.raises(SystemExit, match='Nothing was overwritten'):
        runpy.run_path(script, run_name='__main__')


def test_mac_bundle_no_longer_copies_venv_and_has_versioned_runtime():
    script = (config.ROOT / 'scripts/build-macos-app.sh').read_text()
    assert 'ditto --norsrc .venv' not in script
    assert 'package-runtime.py' in script and 'local-foundry-browser:4' in script
    runtime = (config.ROOT / 'scripts/bootstrap-runtime.py').read_text()
    assert "'--no-index'" in runtime and 'sha256' in runtime and 'flock' in runtime
    with (config.ROOT / 'scripts/macos/Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    assert plist['CFBundleShortVersionString'] == json.loads((config.ROOT / 'frontend/package.json').read_text())['version']


def test_browser_host_allowlist_is_not_overridden():
    vite = (config.ROOT / 'template/frontend/vite.config.js').read_text()
    assert vite.count('allowedHosts:') == 1
    assert "'web'" in vite
