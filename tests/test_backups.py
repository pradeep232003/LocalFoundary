import json

import pytest

from app import backups, files, sandbox


def arrange(tmp_path, monkeypatch):
    project = tmp_path / ('a' * 32)
    source = project / 'source'
    source.mkdir(parents=True)
    files.write(source, 'backend/app/main.py', 'answer = 42')
    monkeypatch.setattr(sandbox, 'project_dir', lambda project_id: project)
    monkeypatch.setattr(sandbox, 'source_dir', lambda project_id: source)
    monkeypatch.setattr(sandbox, 'dump_database',
                        lambda project_id, path: path.write_bytes(b'PGDMP\x01safe-database'))
    return project


def test_backup_is_verified_recorded_and_private(tmp_path, monkeypatch):
    project = arrange(tmp_path, monkeypatch)

    record = backups.create('a' * 32, 'Manual backup')

    dump = project / 'backups' / (record['id'] + '.dump')
    metadata = project / 'backups' / (record['id'] + '.json')
    assert dump.read_bytes().startswith(b'PGDMP')
    assert dump.stat().st_mode & 0o777 == 0o600
    assert metadata.stat().st_mode & 0o777 == 0o600
    assert json.loads(metadata.read_text())['sha256'] == backups.checksum(dump)
    assert backups.listing('a' * 32)[0]['id'] == record['id']


def test_tampered_backup_is_blocked_before_safeguard_or_restore(tmp_path, monkeypatch):
    project = arrange(tmp_path, monkeypatch)
    record = backups.create('a' * 32, 'Manual backup')
    (project / 'backups' / (record['id'] + '.dump')).write_bytes(b'PGDMPtampered')
    monkeypatch.setattr(sandbox, 'restore_database',
                        lambda *args: pytest.fail('restore must not run for a bad checksum'))

    with pytest.raises(ValueError, match='checksum'):
        backups.restore('a' * 32, record['id'])


def test_restore_creates_safeguard_before_database_transfer(tmp_path, monkeypatch):
    project = arrange(tmp_path, monkeypatch)
    record = backups.create('a' * 32, 'Manual backup')
    calls = []
    monkeypatch.setattr(backups, 'create', lambda project_id, label: calls.append(('backup', label)) or {'id': 'safe'})
    monkeypatch.setattr(sandbox, 'restore_database', lambda project_id, path: calls.append(('restore', path.name)))

    result = backups.restore('a' * 32, record['id'])

    assert result == {'id': 'safe'}
    assert calls == [('backup', 'Before database restore'), ('restore', record['id'] + '.dump')]
