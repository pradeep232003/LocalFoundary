"""Encrypted, portable recovery archives for source, history, versions, and PostgreSQL."""
import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import backups, config, continuity_archive, db, files, sandbox

MAGIC = b'LFR1'
MAX_ARCHIVE = 10_000_000_000
MAX_ENTRIES = 2_000
MAX_MANIFEST = 64_000_000
MAX_VERSION_JSON = files.MAX_TOTAL * 3


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_password(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 200:
        raise ValueError('Recovery passwords must contain 12–200 characters.')
    return password


def password_key(password, salt):
    validate_password(password)
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(password.encode('utf-8'))


def folder(project_id):
    path = sandbox.project_dir(project_id) / 'recovery'
    path.mkdir(exist_ok=True)
    path.chmod(0o700)
    return path


def encrypt(source, destination, password):
    if source.stat().st_size > MAX_ARCHIVE - 48:
        raise ValueError('Recovery archive exceeds the supported 10 GB limit.')
    salt, nonce = os.urandom(16), os.urandom(12)
    encryptor = Cipher(algorithms.AES(password_key(password, salt)), modes.GCM(nonce)).encryptor()
    with source.open('rb') as input_stream, destination.open('xb') as output_stream:
        destination.chmod(0o600)
        output_stream.write(MAGIC + salt + nonce)
        while chunk := input_stream.read(1024 * 1024):
            output_stream.write(encryptor.update(chunk))
        output_stream.write(encryptor.finalize())
        output_stream.write(encryptor.tag)


def decrypt(source, destination, password):
    size = source.stat().st_size
    if size < 48 or size > MAX_ARCHIVE:
        raise ValueError('Invalid recovery archive size.')
    with source.open('rb') as input_stream:
        header = input_stream.read(32)
        if header[:4] != MAGIC:
            raise ValueError('This is not a Local Foundry recovery archive.')
        salt, nonce = header[4:20], header[20:32]
        input_stream.seek(-16, os.SEEK_END)
        tag = input_stream.read(16)
        ciphertext_size = size - 32 - 16
        input_stream.seek(32)
        decryptor = Cipher(algorithms.AES(password_key(password, salt)), modes.GCM(nonce, tag)).decryptor()
        try:
            with destination.open('xb') as output_stream:
                destination.chmod(0o600)
                remaining = ciphertext_size
                while remaining:
                    chunk = input_stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('Recovery archive is truncated.')
                    remaining -= len(chunk)
                    output_stream.write(decryptor.update(chunk))
                output_stream.write(decryptor.finalize())
        except InvalidTag:
            destination.unlink(missing_ok=True)
            raise ValueError('Recovery password is incorrect or the archive was modified.') from None


def create(project_id, password):
    project = db.query('SELECT * FROM projects WHERE id=%s', (project_id,), one=True)
    if not project:
        raise ValueError('Project not found.')
    backup = backups.create(project_id, 'Recovery export')
    dump = backups.verified_path(project_id, backup['id'])
    export_id = uuid.uuid4().hex
    base = folder(project_id)
    plaintext = base / (export_id + '.zip.partial')
    encrypted = base / (export_id + '.lfr')
    try:
        source = files.export(sandbox.source_dir(project_id))
        messages = db.query('SELECT role,content,created_at,mode FROM messages WHERE project_id=%s ORDER BY id',
                            (project_id,))
        versions = db.query('SELECT id,label,digest,created_at FROM versions WHERE project_id=%s ORDER BY created_at',
                            (project_id,))
        manifest = {'format': 1, 'created_at': db.now(),
                    'project': {'name': project['name'], 'created_at': project['created_at']},
                    'source_digest': files.digest(sandbox.source_dir(project_id)),
                    'database': {'path': 'database.dump', 'sha256': backups.checksum(dump),
                                 'bytes': dump.stat().st_size},
                    'messages': messages, 'continuity': continuity_archive.export(project_id),
                    'versions': [{k: value for k, value in version.items() if k != 'id'} for version in versions]}
        if len(source) + len(versions) + 2 > MAX_ENTRIES:
            raise ValueError('Recovery archive contains too many source versions.')
        manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
        if len(manifest_bytes) > MAX_MANIFEST:
            raise ValueError('Recovery chat history is too large to export safely.')
        with zipfile.ZipFile(plaintext, 'x', allowZip64=True) as archive:
            archive.writestr('manifest.json', manifest_bytes)
            for path, value in source.items():
                archive.writestr('source/' + path, value)
            for number, version in enumerate(versions):
                snapshot = sandbox.project_dir(project_id) / 'snapshots' / version['id'] / 'files.json'
                if not snapshot.is_file() or snapshot.is_symlink():
                    raise ValueError('A recorded source version is missing; recovery export was stopped.')
                if snapshot.stat().st_size > MAX_VERSION_JSON:
                    raise ValueError('A source version is too large to export safely.')
                archive.write(snapshot, f'versions/{number:04d}.json')
            archive.write(dump, 'database.dump', compress_type=zipfile.ZIP_STORED)
        encrypt(plaintext, encrypted, password)
        digest = checksum(encrypted)
        filename = re.sub(r'[^A-Za-z0-9._-]+', '-', project['name']).strip('-') or 'project'
        filename += '-' + export_id[:8] + '.lfr'
        db.query('''INSERT INTO recovery_exports(id,project_id,filename,bytes,sha256,created_at)
                    VALUES(%s,%s,%s,%s,%s,%s)''',
                 (export_id, project_id, filename, encrypted.stat().st_size, digest, db.now()))
        return {'id': export_id, 'filename': filename, 'bytes': encrypted.stat().st_size,
                'sha256': digest, 'created_at': db.now()}
    except Exception:
        encrypted.unlink(missing_ok=True)
        raise
    finally:
        plaintext.unlink(missing_ok=True)


def listing(project_id):
    return db.query('''SELECT id,filename,bytes,sha256,created_at FROM recovery_exports
                       WHERE project_id=%s ORDER BY created_at DESC''', (project_id,))


def export_path(project_id, export_id):
    sandbox.validate_id(export_id)
    row = db.query('SELECT * FROM recovery_exports WHERE id=%s AND project_id=%s',
                   (export_id, project_id), one=True)
    path = folder(project_id) / (export_id + '.lfr')
    if not row or not path.is_file() or path.is_symlink():
        raise ValueError('Recovery export not found.')
    if checksum(path) != row['sha256']:
        raise ValueError('Recovery export checksum mismatch.')
    return path, row


def validate_zip(archive):
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES or sum(info.file_size for info in infos) > MAX_ARCHIVE:
        raise ValueError('Recovery archive expands beyond the supported limit.')
    seen = set()
    for info in infos:
        path = PurePosixPath(info.filename)
        if path.is_absolute() or any(part in {'', '.', '..'} for part in path.parts):
            raise ValueError('Recovery archive contains an unsafe path.')
        if info.filename in seen:
            raise ValueError('Recovery archive contains a duplicate path.')
        seen.add(info.filename)
    try:
        manifest_info = archive.getinfo('manifest.json')
        if manifest_info.file_size > MAX_MANIFEST:
            raise ValueError('Recovery manifest is too large.')
        manifest = json.loads(archive.read(manifest_info))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError('Recovery manifest is missing or invalid.') from None
    if not isinstance(manifest, dict) or not isinstance(manifest.get('project'), dict):
        raise ValueError('Unsupported recovery archive format.')
    database = manifest.get('database')
    if (manifest.get('format') != 1 or not isinstance(manifest['project'].get('name'), str) or
            not isinstance(manifest.get('messages', []), list) or
            not isinstance(manifest.get('versions', []), list) or not isinstance(database, dict) or
            not isinstance(database.get('path'), str) or not isinstance(database.get('bytes'), int) or
            database['bytes'] < 5 or database['bytes'] > MAX_ARCHIVE or
            not isinstance(database.get('sha256'), str) or
            not re.fullmatch(r'[0-9a-f]{64}', database['sha256'])):
        raise ValueError('Unsupported recovery archive format.')
    if (any(not isinstance(row, dict) for row in manifest.get('messages', [])) or
            any(not isinstance(row, dict) for row in manifest.get('versions', [])) or
            database['path'] != 'database.dump'):
        raise ValueError('Invalid recovery metadata.')
    return manifest


def import_archive(encrypted_path, password, name=None):
    temporary_root = Path(tempfile.mkdtemp(prefix='foundry-import-', dir=config.DATA))
    plaintext = temporary_root / 'archive.zip'
    project_id = uuid.uuid4().hex
    base = config.PROJECTS / project_id
    try:
        decrypt(encrypted_path, plaintext, password)
        try:
            archive_context = zipfile.ZipFile(plaintext)
        except zipfile.BadZipFile:
            raise ValueError('Recovery archive payload is not a valid ZIP file.') from None
        with archive_context as archive:
            manifest = validate_zip(archive)
            source_entries = [info for info in archive.infolist() if info.filename.startswith('source/') and not info.is_dir()]
            if not source_entries or len(source_entries) > files.MAX_FILES:
                raise ValueError('Recovery source file count is invalid.')
            relative_sources = [info.filename.removeprefix('source/') for info in source_entries]
            if len(set(relative_sources)) != len(relative_sources):
                raise ValueError('Recovery source contains duplicate paths.')
            base.mkdir()
            source = base / 'source'
            source.mkdir()
            total = 0
            for info in source_entries:
                relative_path = info.filename.removeprefix('source/')
                files.relative(relative_path)
                if info.file_size > files.MAX_FILE or total + info.file_size > files.MAX_TOTAL:
                    raise ValueError('Recovery source exceeds the supported size.')
                value = archive.read(info)
                total += len(value)
                if len(value) > files.MAX_FILE or total > files.MAX_TOTAL:
                    raise ValueError('Recovery source exceeds the supported size.')
                try:
                    text = value.decode('utf-8')
                except UnicodeDecodeError:
                    raise ValueError('Recovery source contains a non-text file.') from None
                if files.SECRET.search(text):
                    raise ValueError('Recovery source contains a possible secret.')
                destination = source / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(text)
            files.ensure_layout(source)
            if files.digest(source) != manifest.get('source_digest'):
                raise ValueError('Recovery source checksum mismatch.')
            (base / 'snapshots').mkdir()
            restored_versions = []
            version_entries = sorted((info for info in archive.infolist()
                                      if info.filename.startswith('versions/') and not info.is_dir()),
                                     key=lambda info: info.filename)
            metadata_versions = manifest.get('versions', [])
            if len(version_entries) != len(metadata_versions):
                raise ValueError('Recovery source-version metadata is incomplete.')
            for number, info in enumerate(version_entries):
                if info.filename != f'versions/{number:04d}.json':
                    raise ValueError('Recovery source-version numbering is invalid.')
                if info.file_size > MAX_VERSION_JSON:
                    raise ValueError('A recovery source version is too large.')
                try:
                    content = json.loads(archive.read(info))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise ValueError('A recovery source version is invalid.') from None
                if not isinstance(content, dict):
                    raise ValueError('Invalid source version in recovery archive.')
                version_id = uuid.uuid4().hex
                version_dir = base / 'snapshots' / version_id
                version_dir.mkdir()
                (version_dir / 'files.json').write_text(json.dumps(content))
                # Exercise the normal validator without replacing imported source.
                probe = temporary_root / ('version-' + version_id)
                probe.mkdir()
                files.restore(probe, version_dir)
                shutil.rmtree(probe)
                meta = metadata_versions[number] if number < len(metadata_versions) else {}
                snapshot_digest = files.digest_from_content(content)
                if meta.get('digest') != snapshot_digest:
                    raise ValueError('Recovery source-version checksum mismatch.')
                restored_versions.append((version_id, str(meta.get('label', 'Recovered version'))[:200],
                                          snapshot_digest,
                                          str(meta.get('created_at', db.now()))[:80]))
            (base / 'backups').mkdir()
            (base / 'recovery').mkdir()
            try:
                dump_info = archive.getinfo(manifest['database']['path'])
            except KeyError:
                raise ValueError('Recovery database dump is missing.') from None
            if dump_info.is_dir() or dump_info.file_size != manifest['database']['bytes']:
                raise ValueError('Recovery database size does not match its manifest.')
            dump = temporary_root / 'database.dump'
            with archive.open(dump_info) as source_stream, dump.open('xb') as destination_stream:
                shutil.copyfileobj(source_stream, destination_stream, length=1024 * 1024)
            dump.chmod(0o600)
            with dump.open('rb') as stream:
                if stream.read(5) != b'PGDMP':
                    raise ValueError('Recovery database is not a PostgreSQL custom-format dump.')
            if checksum(dump) != manifest['database']['sha256']:
                raise ValueError('Recovery database checksum mismatch.')
        sandbox.restore_database(project_id, dump)
        project_name = (name or manifest['project']['name']).strip()[:80]
        if not project_name:
            raise ValueError('Recovered project needs a name.')
        statements = [('INSERT INTO projects(id,name,created_at) VALUES(%s,%s,%s)',
                       (project_id, project_name, db.now()))]
        statements.extend(continuity_archive.statements(project_id, manifest.get('continuity')))
        for message in manifest.get('messages', []):
            if message.get('role') in {'user', 'assistant'} and isinstance(message.get('content'), str):
                statements.append(('''INSERT INTO messages(project_id,role,content,created_at,mode)
                            VALUES(%s,%s,%s,%s,%s)''',
                         (project_id, message['role'], message['content'][:24000],
                          str(message.get('created_at', db.now()))[:80],
                          message.get('mode') if message.get('mode') in {'coder', 'documents', 'files'} else 'coder')))
        if not restored_versions:
            version_id = uuid.uuid4().hex
            digest = files.snapshot(source, base / 'snapshots' / version_id)
            restored_versions.append((version_id, 'Recovered source', digest, db.now()))
        for version in restored_versions:
            statements.append(('INSERT INTO versions(id,project_id,label,digest,created_at) VALUES(%s,%s,%s,%s,%s)',
                               (version[0], project_id, version[1], version[2], version[3])))
        db.batch(statements)
        return {'id': project_id, 'name': project_name}
    except Exception:
        if base.exists():
            try:
                sandbox.command(project_id, 'down', '--timeout', '3', '--volumes', timeout=30)
            except Exception:
                pass
            shutil.rmtree(base, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)
