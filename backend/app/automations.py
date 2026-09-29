"""Dry-run-first, reversible file organization inside one managed folder."""
import hashlib
import json
import os
import threading
import uuid
from pathlib import Path, PurePosixPath

from . import config, db

MAX_FILES = 5_000
MAX_OPERATIONS = 100
lock = threading.Lock()


def relative(value):
    if not isinstance(value, str) or not value or len(value) > 400 or '\\' in value or '\x00' in value:
        raise ValueError('Invalid managed file path.')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {'', '.', '..'} or part.startswith('.') for part in path.parts):
        raise ValueError('Managed paths must be visible relative paths inside the files folder.')
    return path


def target(value):
    path = relative(value)
    root = config.AUTOMATION_FILES.resolve()
    result = (root / path).resolve()
    if not result.is_relative_to(root):
        raise ValueError('Managed path escapes the files folder.')
    cursor = root
    for part in path.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('Symlinks are not supported by file automation.')
    return result


def inventory():
    rows = []
    for directory, dirs, names in os.walk(config.AUTOMATION_FILES, followlinks=False):
        dirs[:] = [name for name in dirs if not name.startswith('.') and not (Path(directory) / name).is_symlink()]
        for name in names:
            path = Path(directory) / name
            if name.startswith('.') or path.is_symlink() or not path.is_file():
                continue
            stat = path.stat()
            rows.append({'path': path.relative_to(config.AUTOMATION_FILES).as_posix(),
                         'bytes': stat.st_size, 'modified_ns': stat.st_mtime_ns})
            if len(rows) > MAX_FILES:
                raise ValueError('The managed files folder exceeds 5,000 files.')
    return sorted(rows, key=lambda item: item['path'])


def workspace_digest():
    # File contents are never opened by the automation subsystem. Paths, sizes,
    # and nanosecond mtimes are enough to fail closed when the visible workspace
    # changes between preview, apply, and undo.
    return hashlib.sha256(json.dumps(inventory(), sort_keys=True).encode()).hexdigest()


def validate_operations(operations):
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise ValueError('A file plan must contain 1–100 operations.')
    existing = {item['path'] for item in inventory()}
    directories = {'.'}
    for directory, names, _ in os.walk(config.AUTOMATION_FILES, followlinks=False):
        names[:] = [name for name in names if not name.startswith('.') and not (Path(directory) / name).is_symlink()]
        relative_directory = Path(directory).relative_to(config.AUTOMATION_FILES).as_posix()
        directories.add(relative_directory or '.')
    normalized = []
    used_sources = set()
    for raw in operations:
        if not isinstance(raw, dict) or raw.get('op') not in {'move', 'trash', 'mkdir'}:
            raise ValueError('File plans support move, trash, and mkdir operations only.')
        operation = raw['op']
        if operation == 'mkdir':
            destination = relative(raw.get('destination')).as_posix()
            parent = str(PurePosixPath(destination).parent)
            if parent not in directories:
                raise ValueError('Create the parent directory first: ' + parent)
            if destination in existing or destination in directories or target(destination).exists():
                raise ValueError('Directory destination already exists: ' + destination)
            directories.add(destination)
            normalized.append({'op': 'mkdir', 'destination': destination})
            continue
        source = relative(raw.get('source')).as_posix()
        if source in used_sources or source not in existing or not target(source).is_file():
            raise ValueError('File source is missing or repeated: ' + source)
        used_sources.add(source)
        existing.remove(source)
        if operation == 'trash':
            normalized.append({'op': 'trash', 'source': source})
            continue
        destination = relative(raw.get('destination')).as_posix()
        if str(PurePosixPath(destination).parent) not in directories:
            raise ValueError('Create the destination directory first: ' + str(PurePosixPath(destination).parent))
        if destination in existing or target(destination).exists():
            raise ValueError('File destination already exists: ' + destination)
        existing.add(destination)
        normalized.append({'op': 'move', 'source': source, 'destination': destination})
    return normalized


def create_plan(project_id, prompt, operations):
    normalized = validate_operations(operations)
    plan_id = uuid.uuid4().hex
    db.query('''INSERT INTO file_plans(id,project_id,prompt,operations,status,workspace_digest,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s)''',
             (plan_id, project_id, prompt[:12000], json.dumps(normalized), 'planned',
              workspace_digest(), db.now()))
    return get(plan_id, project_id)


def get(plan_id, project_id=None):
    row = db.query('SELECT * FROM file_plans WHERE id=%s' + (' AND project_id=%s' if project_id else ''),
                   (plan_id, project_id) if project_id else (plan_id,), one=True)
    if not row:
        raise ValueError('File plan not found.')
    row['operations'] = json.loads(row['operations'])
    row['undo_data'] = json.loads(row['undo_data']) if row.get('undo_data') else None
    return row


def listing(project_id):
    rows = db.query('SELECT * FROM file_plans WHERE project_id=%s ORDER BY created_at DESC LIMIT 20', (project_id,))
    for row in rows:
        row['operations'] = json.loads(row['operations'])
        row['undo_data'] = None
    return rows


def reverse(actions):
    for action in reversed(actions):
        if action['op'] == 'move':
            current, destination = target(action['source']), target(action['destination'])
            if current.exists() and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                current.replace(destination)
        elif action['op'] == 'rmdir':
            directory = target(action['path'])
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()


def apply(plan_id, project_id):
    with lock:
        plan = get(plan_id, project_id)
        if plan['status'] != 'planned':
            raise ValueError('Only a pending file plan can be applied.')
        if workspace_digest() != plan['workspace_digest']:
            raise ValueError('Managed files changed after the preview. Create a fresh plan.')
        undo = []
        try:
            for operation in plan['operations']:
                if operation['op'] == 'mkdir':
                    target(operation['destination']).mkdir(exist_ok=False)
                    undo.append({'op': 'rmdir', 'path': operation['destination']})
                elif operation['op'] == 'move':
                    source, destination = target(operation['source']), target(operation['destination'])
                    source.replace(destination)
                    undo.append({'op': 'move', 'source': operation['destination'],
                                 'destination': operation['source']})
                else:
                    source = target(operation['source'])
                    trash = config.AUTOMATION_FILES / '.foundry-trash' / plan_id / relative(operation['source'])
                    trash.parent.mkdir(parents=True, exist_ok=True)
                    source.replace(trash)
                    undo.append({'op': 'trash_restore',
                                 'destination': operation['source']})
            payload = {'actions': undo, 'post_digest': workspace_digest()}
            db.query('UPDATE file_plans SET status=%s,undo_data=%s,applied_at=%s WHERE id=%s',
                     ('applied', json.dumps(payload), db.now(), plan_id))
        except Exception:
            # Translate trash paths for rollback without exposing the hidden root to normal target().
            for action in reversed(undo):
                if action['op'] == 'trash_restore':
                    hidden = config.AUTOMATION_FILES / '.foundry-trash' / plan_id / relative(action['destination'])
                    destination = target(action['destination'])
                    if hidden.exists() and not destination.exists():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        hidden.replace(destination)
                else:
                    reverse([action])
            raise
        return get(plan_id, project_id)


def undo(plan_id, project_id):
    with lock:
        plan = get(plan_id, project_id)
        if plan['status'] != 'applied' or not plan['undo_data']:
            raise ValueError('Only an applied file plan can be undone.')
        if workspace_digest() != plan['undo_data']['post_digest']:
            raise ValueError('Managed files changed after this plan. Automatic undo was blocked.')
        completed = []
        try:
            for action in reversed(plan['undo_data']['actions']):
                if action['op'] == 'trash_restore':
                    hidden = config.AUTOMATION_FILES / '.foundry-trash' / plan_id / relative(action['destination'])
                    destination = target(action['destination'])
                    if not hidden.is_file() or destination.exists():
                        raise ValueError('A trashed file cannot be restored safely: ' + action['destination'])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    hidden.replace(destination)
                    completed.append({'op': 'trash_back', 'path': action['destination']})
                elif action['op'] == 'move':
                    source, destination = target(action['source']), target(action['destination'])
                    if not source.is_file() or destination.exists():
                        raise ValueError('A moved file cannot be restored safely: ' + action['destination'])
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    source.replace(destination)
                    completed.append({'op': 'move', 'source': action['destination'], 'destination': action['source']})
                else:
                    directory = target(action['path'])
                    if not directory.is_dir() or any(directory.iterdir()):
                        raise ValueError('A created directory is no longer empty: ' + action['path'])
                    directory.rmdir()
                    completed.append({'op': 'mkdir', 'destination': action['path']})
            db.query('UPDATE file_plans SET status=%s WHERE id=%s', ('undone', plan_id))
        except Exception:
            for action in reversed(completed):
                try:
                    if action['op'] == 'trash_back':
                        source = target(action['path'])
                        hidden = config.AUTOMATION_FILES / '.foundry-trash' / plan_id / relative(action['path'])
                        hidden.parent.mkdir(parents=True, exist_ok=True)
                        if source.exists() and not hidden.exists():
                            source.replace(hidden)
                    elif action['op'] == 'move':
                        source, destination = target(action['source']), target(action['destination'])
                        if source.exists() and not destination.exists():
                            source.replace(destination)
                    else:
                        target(action['destination']).mkdir(exist_ok=True)
                except Exception:
                    pass
            raise
        return get(plan_id, project_id)
