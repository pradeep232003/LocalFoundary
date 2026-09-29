import hashlib
import json
import uuid

from . import db, files, sandbox


def folder(project_id):
    path = sandbox.project_dir(project_id) / 'backups'
    path.mkdir(exist_ok=True)
    path.chmod(0o700)
    return path


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def create(project_id, label):
    backup_id = uuid.uuid4().hex
    base = folder(project_id)
    temporary = base / (backup_id + '.partial')
    path = base / (backup_id + '.dump')
    metadata = base / (backup_id + '.json')
    temporary_metadata = base / (backup_id + '.json.partial')
    try:
        sandbox.dump_database(project_id, temporary)
        temporary.chmod(0o600)
        with temporary.open('rb') as stream:
            if stream.read(5) != b'PGDMP':
                raise RuntimeError('PostgreSQL returned an invalid backup. Existing backups were preserved.')
        record = {'id': backup_id, 'label': label, 'created_at': db.now(), 'bytes': temporary.stat().st_size,
                  'sha256': checksum(temporary), 'source_digest': files.digest(sandbox.source_dir(project_id))}
        temporary_metadata.write_text(json.dumps(record))
        temporary_metadata.chmod(0o600)
        temporary.replace(path)
        temporary_metadata.replace(metadata)
        return record
    except Exception:
        temporary.unlink(missing_ok=True)
        temporary_metadata.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        raise


def listing(project_id):
    return sorted([json.loads(p.read_text()) for p in folder(project_id).glob('*.json')],
                  key=lambda r: r['created_at'], reverse=True)


def verified_path(project_id, backup_id):
    sandbox.validate_id(backup_id)
    base = folder(project_id)
    metadata, path = base / (backup_id + '.json'), base / (backup_id + '.dump')
    if (not metadata.is_file() or not path.is_file() or metadata.is_symlink() or path.is_symlink()):
        raise ValueError('Backup not found.')
    record = json.loads(metadata.read_text())
    if record.get('id') != backup_id or checksum(path) != record.get('sha256'):
        raise ValueError('Backup checksum mismatch. Restore was blocked.')
    return path


def restore(project_id, backup_id):
    path = verified_path(project_id, backup_id)
    safeguard = create(project_id, 'Before database restore')
    sandbox.restore_database(project_id, path)
    return safeguard
