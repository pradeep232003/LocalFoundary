import hashlib
import json
import zipfile

import pytest

from app import backups, config, db, files, main, recovery, sandbox


def test_streaming_encryption_round_trip_and_wrong_password(tmp_path):
    source = tmp_path / 'source.zip'
    source.write_bytes(b'private recovery bytes' * 1000)
    encrypted = tmp_path / 'project.lfr'
    restored = tmp_path / 'restored.zip'
    recovery.encrypt(source, encrypted, 'correct horse battery staple')
    assert encrypted.read_bytes().startswith(recovery.MAGIC)
    assert b'private recovery bytes' not in encrypted.read_bytes()
    recovery.decrypt(encrypted, restored, 'correct horse battery staple')
    assert restored.read_bytes() == source.read_bytes()

    with pytest.raises(ValueError, match='incorrect|modified'):
        recovery.decrypt(encrypted, tmp_path / 'wrong.zip', 'this password is wrong')


def test_import_creates_new_project_without_repository_connection(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    projects = data / 'projects'
    projects.mkdir(parents=True)
    monkeypatch.setattr(config, 'DATA', data)
    monkeypatch.setattr(config, 'PROJECTS', projects)
    content = {'backend/app/main.py': 'answer = 42\n'}
    database = b'PGDMP\x01portable-data'
    manifest = {'format': 1, 'created_at': 'now',
        'project': {'name': 'Recovered notebook', 'created_at': 'then'},
        'source_digest': files.digest_from_content(content),
        'database': {'path': 'database.dump', 'sha256': hashlib.sha256(database).hexdigest(),
                     'bytes': len(database)},
        'messages': [{'role': 'user', 'content': 'Original request', 'created_at': 'then', 'mode': 'coder'}],
        'versions': []}
    plain = tmp_path / 'plain.zip'
    with zipfile.ZipFile(plain, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('source/backend/app/main.py', content['backend/app/main.py'])
        archive.writestr('database.dump', database)
    encrypted = tmp_path / 'project.lfr'
    recovery.encrypt(plain, encrypted, 'correct horse battery staple')
    restored = []
    queries = []
    monkeypatch.setattr(sandbox, 'restore_database', lambda project_id, path: restored.append((project_id, path.read_bytes())))
    monkeypatch.setattr(recovery.db, 'query', lambda sql, params=(), one=False: queries.append((sql, params)))
    monkeypatch.setattr(recovery.db, 'batch', lambda statements: queries.extend(statements))
    monkeypatch.setattr(recovery.db, 'now', lambda: 'import-time')

    result = recovery.import_archive(encrypted, 'correct horse battery staple', 'Imported copy')

    assert result['name'] == 'Imported copy'
    assert restored[0][1] == database
    assert files.read(projects / result['id'] / 'source', 'backend/app/main.py') == 'answer = 42\n'
    project_insert = next(params for sql, params in queries if sql.startswith('INSERT INTO projects'))
    assert project_insert[1] == 'Imported copy'
    assert all('repo' not in sql.lower() for sql, _ in queries)


def test_zip_path_traversal_is_rejected(tmp_path):
    path = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps({'format': 1, 'project': {'name': 'x'}}))
        archive.writestr('../outside.txt', 'bad')
    with zipfile.ZipFile(path) as archive:
        with pytest.raises(ValueError, match='unsafe path'):
            recovery.validate_zip(archive)


def test_duplicate_archive_paths_are_rejected(tmp_path):
    path = tmp_path / 'duplicate.zip'
    manifest = {'format': 1, 'project': {'name': 'x'}, 'messages': [], 'versions': [],
                'database': {'path': 'database.dump', 'bytes': 5, 'sha256': '0' * 64}}
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('database.dump', b'PGDMP')
        with pytest.warns(UserWarning, match='Duplicate name'):
            archive.writestr('database.dump', b'PGDMP')
    with zipfile.ZipFile(path) as archive:
        with pytest.raises(ValueError, match='duplicate path'):
            recovery.validate_zip(archive)


def test_encrypted_export_import_preserves_multiple_version_order(client, tmp_path, monkeypatch):
    pid = client.post('/api/projects', json={'name': 'Three versions'}).json()['id']
    for number in (2, 3):
        files.write(sandbox.source_dir(pid), 'backend/app/version.py', f'version = {number}\n')
        main.save_version(pid, f'Version {number}')
    dump = tmp_path / 'backup.dump'
    dump.write_bytes(b'PGDMP-real-transfer-mocked')
    monkeypatch.setattr(backups, 'create', lambda *args: {'id': 'a'*32})
    monkeypatch.setattr(backups, 'verified_path', lambda *args: dump)
    restores = []
    monkeypatch.setattr(sandbox, 'restore_database', lambda pid, path: restores.append(path.read_bytes()))
    exported = recovery.create(pid, 'correct horse battery staple')
    encrypted, _ = recovery.export_path(pid, exported['id'])
    result = recovery.import_archive(encrypted, 'correct horse battery staple')
    versions = db.query('SELECT * FROM versions WHERE project_id=%s ORDER BY created_at', (result['id'],))
    assert [row['label'] for row in versions] == ['Starting template', 'Version 2', 'Version 3']
    assert len(restores) == 1 and restores[0] == dump.read_bytes()
    for row in versions:
        snapshot = sandbox.project_dir(result['id']) / 'snapshots' / row['id'] / 'files.json'
        assert files.digest_from_content(json.loads(snapshot.read_text())) == row['digest']


def test_recovery_metadata_batch_rolls_back(client):
    pid = '9' * 32
    with pytest.raises(Exception):
        db.batch([('INSERT INTO projects(id,name,created_at) VALUES(%s,%s,%s)', (pid, 'first', 'now')),
                  ('INSERT INTO projects(id,name,created_at) VALUES(%s,%s,%s)', (pid, 'duplicate', 'now'))])
    assert db.query('SELECT * FROM projects WHERE id=%s', (pid,), one=True) is None


@pytest.mark.parametrize('manifest', [[], {'project': []}, {'project': None}])
def test_malformed_nested_recovery_manifest_is_rejected(tmp_path, manifest):
    path = tmp_path / 'invalid.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
    with zipfile.ZipFile(path) as archive:
        with pytest.raises(ValueError, match='Unsupported recovery'):
            recovery.validate_zip(archive)
