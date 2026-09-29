import json

import pytest
from app import files


@pytest.mark.parametrize('path', ['../.env', '/etc/passwd', 'frontend/src/../../.env',
    'backend/app/../../../outside.py', 'frontend/src/.env', 'frontend/src/.git/config',
    'frontend/src/credentials.json', 'frontend\\src\\a.js', 'compose.json',
    'frontend/package.json', 'frontend/vite.config.js', 'backend/Dockerfile', '.gitignore'])
def test_agent_cannot_write_outside_source(tmp_path, path):
    with pytest.raises(ValueError):
        files.write(tmp_path, path, 'unsafe')


def test_symlink_parent_cannot_read_or_overwrite_host_file(tmp_path):
    source, outside = tmp_path / 'source', tmp_path / 'outside'
    (source / 'backend').mkdir(parents=True)
    outside.mkdir()
    (outside / 'private.py').write_text('private information')
    (source / 'backend/app').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        files.read(source, 'backend/app/private.py')
    with pytest.raises(ValueError):
        files.write(source, 'backend/app/private.py', 'overwrite')
    assert (outside / 'private.py').read_text() == 'private information'
    assert not files.export(source)


def test_secret_and_oversized_content_rejected(tmp_path):
    with pytest.raises(ValueError, match='keys'):
        files.write(tmp_path, 'backend/app/main.py', 'sk-ant-' + 'a' * 40)
    with pytest.raises(ValueError, match='256'):
        files.write(tmp_path, 'frontend/src/App.jsx', 'a' * (files.MAX_FILE + 1))


def test_export_excludes_secrets_and_unmanaged_data(tmp_path):
    files.write(tmp_path, 'backend/app/main.py', 'answer = 42')
    (tmp_path / '.env').write_text('password=private')
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/private.txt').write_text('a private note')
    assert files.export(tmp_path) == {'backend/app/main.py': 'answer = 42'}


def test_snapshot_restores_deleted_and_modified_files(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    files.write(source, 'backend/app/main.py', 'version = 1')
    files.snapshot(source, tmp_path / 'snapshot')
    files.write(source, 'backend/app/main.py', 'version = 2')
    files.write(source, 'frontend/src/new.jsx', 'new feature')
    files.restore(source, tmp_path / 'snapshot')
    assert files.export(source) == {'backend/app/main.py': 'version = 1'}
    # Empty bind-mount targets are not represented in the JSON snapshot, but
    # must exist after restore or Docker Compose refuses to start the preview.
    for directory in files.REQUIRED_DIRS:
        assert (source / directory).is_dir()


def test_invalid_snapshot_does_not_damage_existing_source(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    files.write(source, 'backend/app/main.py', 'keep = True')
    snapshot = tmp_path / 'snapshot'; snapshot.mkdir()
    (snapshot / 'files.json').write_text(json.dumps({'../../escape.py': 'bad'}))
    with pytest.raises(ValueError):
        files.restore(source, snapshot)
    assert files.read(source, 'backend/app/main.py') == 'keep = True'
