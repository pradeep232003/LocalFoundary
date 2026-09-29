"""Regression checks on an extracted distribution, including the Accounts starter."""
import hashlib
import json
from pathlib import Path
import runpy
import zipfile

import pytest

from app import config, profiles, sandbox


@pytest.fixture
def packager():
    return runpy.run_path(str(config.ROOT / 'scripts/package-source.py'))


def test_extracted_distribution_can_create_accounts_project(packager, tmp_path, monkeypatch):
    archive = tmp_path / 'source.zip'
    packager['build_archive'](config.ROOT, archive)
    extracted = tmp_path / 'extracted'
    with zipfile.ZipFile(archive) as zipped:
        manifest = json.loads(zipped.read('local-foundry/SOURCE-MANIFEST.json'))
        assert len(zipped.namelist()) == len(manifest['files']) + 1
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(zipped.read('local-foundry/' + name)).hexdigest() == digest
        # Every kit file must survive packaging, including migrations and UI.
        for path in (config.ROOT / 'kits/accounts').rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                assert path.relative_to(config.ROOT).as_posix() in manifest['files']
        assert zipped.getinfo('local-foundry/scripts/setup.sh').external_attr >> 16 & 0o111
        zipped.extractall(extracted)
    monkeypatch.setattr(config, 'ROOT', extracted / 'local-foundry')
    monkeypatch.setattr(config, 'PROJECTS', tmp_path / 'projects')
    config.PROJECTS.mkdir()
    project_id = 'b' * 32
    sandbox.seed(project_id, 'accounts')
    source = sandbox.source_dir(project_id)
    assert profiles.get(source) == 'accounts'
    assert (source / 'backend/app/auth.py').is_file()
    assert (source / 'backend/migrations/002_accounts.sql').is_file()
    assert (source / 'frontend/src/workspace.css').is_file()
    compose = json.loads((source / 'compose.json').read_text())
    assert compose['services']['api']['environment']['PAYMENT_MODE'] == 'off'


def fixture_source(packager, root):
    for name in packager['CODE_DIRS']:
        (root / name).mkdir(parents=True)
    for name in packager['REQUIRED']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}' if name == 'frontend/package.json' else 'fixture')
    (root / 'frontend/package.json').write_text('{"version":"0.10.1"}')
    return root


def test_packaging_excludes_private_files_without_dropping_named_source_folders(packager, tmp_path):
    source = fixture_source(packager, tmp_path / 'source')
    excluded = ['backend/.env', 'backend/.env.local', 'backend/cache.pyc', 'backend/private.key',
                'frontend/node_modules/private.txt', 'frontend/dist/build.js',
                'screenshots/ui/capture.png', 'screenshots/accounts/capture.png',
                '.data/private.txt']
    included = ['backend/accounts/example.py', 'frontend/src/ui/example.jsx']
    for name in excluded + included:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
    (source / 'backend/linked.py').symlink_to(source / 'backend/.env')
    archive = tmp_path / 'source.zip'
    packager['build_archive'](source, archive)
    with zipfile.ZipFile(archive) as zipped:
        names = set(zipped.namelist())
        assert all('local-foundry/' + name not in names for name in excluded + ['backend/linked.py'])
        assert all('local-foundry/' + name in names for name in included)
        assert 'local-foundry/kits/accounts/backend/app/auth.py' in names


def test_incomplete_source_does_not_replace_existing_archive(packager, tmp_path):
    source = fixture_source(packager, tmp_path / 'source')
    (source / 'kits/accounts/backend/app/auth.py').unlink()
    archive = tmp_path / 'source.zip'
    archive.write_bytes(b'previous release')
    with pytest.raises(ValueError, match='Missing required source'):
        packager['build_archive'](source, archive)
    assert archive.read_bytes() == b'previous release'


def test_packaging_includes_only_matching_report_and_referenced_logs(packager, tmp_path):
    source = fixture_source(packager, tmp_path / 'source')
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    report = {'version': '0.10.1', 'checks': [{'name': 'unit', 'log': '1.log'}]}
    (evidence / 'acceptance.json').write_text(json.dumps(report))
    for name in ('ACCEPTANCE.md', '1.log', '2.log'):
        (evidence / name).write_text('fixture')
    archive = tmp_path / 'source.zip'
    packager['build_archive'](source, archive, evidence)
    with zipfile.ZipFile(archive) as zipped:
        logs = {Path(name).name for name in zipped.namelist() if name.endswith('.log')}
        assert logs == {'1.log'}
    report['version'] = '0.7.0'
    (evidence / 'acceptance.json').write_text(json.dumps(report))
    with pytest.raises(ValueError, match='must match the source version'):
        packager['build_archive'](source, archive, evidence)
