"""The only host-file boundary exposed to the model. No arbitrary host paths."""
import hashlib
import json
import os
import re
import shutil
import stat
import uuid
from pathlib import Path, PurePosixPath

MAX_FILE = 256_000
MAX_TOTAL = 5_000_000
MAX_FILES = 400
REQUIRED_DIRS = ('frontend/src', 'frontend/public', 'backend/app', 'backend/tests', 'backend/migrations')
EDIT_ROOTS = ('frontend/src/', 'frontend/public/', 'backend/app/', 'backend/tests/', 'backend/migrations/')
READ_FILES = {'frontend/package.json', 'frontend/package-lock.json', 'frontend/index.html', 'frontend/vite.config.js',
              'backend/requirements.txt', 'backend/requirements-lock.txt', 'backend/foundry.json', 'backend/PLATFORM.md', 'README.md', 'compose.json', '.gitignore',
              'frontend/Dockerfile', 'backend/Dockerfile', 'backend/runtime.py'}
EXTENSIONS = {'.py', '.js', '.jsx', '.ts', '.tsx', '.css', '.json', '.html', '.md', '.txt', '.svg', '.sql'}
SECRET = re.compile(r'(?:sk-(?:ant-)?[A-Za-z0-9_-]{24,}|(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}|whsec_[A-Za-z0-9]{20,}|re_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def relative(path: str, write=False) -> PurePosixPath:
    if not isinstance(path, str) or not path or len(path) > 240 or '\\' in path or '\x00' in path:
        raise ValueError('Invalid project path.')
    p = PurePosixPath(path)
    if p.is_absolute() or any(x in {'.', '..'} for x in path.split('/')):
        raise ValueError('Paths must stay inside the project.')
    if any(x.startswith('.') for x in p.parts) and path != '.gitignore':
        raise ValueError('Hidden files are not accessible.')
    editable = path.startswith(EDIT_ROOTS) and p.suffix in EXTENSIONS
    if not editable and (write or path not in READ_FILES):
        raise ValueError('Only app source can be edited. Runtime configuration is managed by the builder.')
    if p.name.lower().startswith(('credentials', 'secrets')):
        raise ValueError('Credential files are not part of app source.')
    return p


def target(root: Path, path: str, write=False) -> Path:
    p = relative(path, write)
    cursor = root
    if root.is_symlink():
        raise ValueError('Symlink project roots are forbidden.')
    for part in p.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError('Symlinks are forbidden in app source.')
    if not cursor.resolve().is_relative_to(root.resolve()):
        raise ValueError('Path escapes the project.')
    return cursor


def list_files(root: Path) -> list[str]:
    paths = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', 'dist', '__pycache__'}
                   and not (Path(directory) / d).is_symlink()]
        for name in files:
            path = (Path(directory) / name).relative_to(root).as_posix()
            try:
                relative(path)
                target(root, path)
                paths.append(path)
            except ValueError:
                continue
    if len(paths) > MAX_FILES:
        raise ValueError('Project exceeds 400 source files.')
    return sorted(paths)


def read(root: Path, path: str) -> str:
    p = target(root, path)
    if not stat.S_ISREG(p.stat().st_mode) or p.stat().st_size > MAX_FILE:
        raise ValueError('Only text files up to 256 KB are supported.')
    return p.read_text(encoding='utf-8')


def export(root: Path) -> dict[str, str]:
    result, total = {}, 0
    for path in list_files(root):
        content = read(root, path)
        total += len(content.encode())
        if SECRET.search(content):
            raise ValueError(f'Possible secret in {path}. Remove it before exporting.')
        result[path] = content
    if total > MAX_TOTAL:
        raise ValueError('Project exceeds the 5 MB text-source limit.')
    return result


def write(root: Path, path: str, content: str) -> str:
    p = target(root, path, write=True)
    if not isinstance(content, str) or len(content.encode()) > MAX_FILE:
        raise ValueError('Files must be text and no larger than 256 KB.')
    if SECRET.search(content):
        raise ValueError('Do not put API keys or private keys in generated code.')
    current = list_files(root)
    if path not in current and len(current) >= MAX_FILES:
        raise ValueError('Project file limit reached.')
    size = sum(target(root, f).stat().st_size for f in current if f != path)
    if size + len(content.encode()) > MAX_TOTAL:
        raise ValueError('Project size limit reached.')
    p.parent.mkdir(parents=True, exist_ok=True)
    temporary = p.with_name('.write-' + uuid.uuid4().hex)
    try:
        temporary.write_text(content, encoding='utf-8')
        temporary.replace(p)
    finally:
        temporary.unlink(missing_ok=True)
    return f'Wrote {path} ({len(content.encode())} bytes)'


def delete(root: Path, path: str):
    target(root, path, write=True).unlink()
    return f'Deleted {path}'


def snapshot(source: Path, destination: Path):
    content = export(source)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'files.json').write_text(json.dumps(content), encoding='utf-8')
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def digest(source: Path):
    return hashlib.sha256(json.dumps(export(source), sort_keys=True).encode()).hexdigest()


def digest_from_content(content):
    if not isinstance(content, dict):
        raise ValueError('Invalid source snapshot.')
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def ensure_layout(source: Path):
    for folder in REQUIRED_DIRS:
        path = source / folder
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != source.parent):
            raise ValueError('Symlink directories cannot be mounted.')
        path.mkdir(parents=True, exist_ok=True)


def restore(source: Path, snapshot_dir: Path):
    """Validate the whole snapshot first; callers hold a project lock and stop previews."""
    content = json.loads((snapshot_dir / 'files.json').read_text())
    if not isinstance(content, dict) or len(content) > MAX_FILES:
        raise ValueError('Invalid snapshot file count.')
    if sum(len(v.encode()) for v in content.values() if isinstance(v, str)) > MAX_TOTAL:
        raise ValueError('Invalid snapshot size.')
    for path, value in content.items():
        relative(path)
        if not isinstance(value, str) or len(value.encode()) > MAX_FILE or SECRET.search(value):
            raise ValueError('Invalid snapshot content.')
    staging = source.parent / ('restore-' + uuid.uuid4().hex)
    staging.mkdir()
    try:
        for path, value in content.items():
            p = staging / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value, encoding='utf-8')
        ensure_layout(staging)
    except Exception:
        shutil.rmtree(staging)
        raise
    old = source.with_name('old-' + uuid.uuid4().hex)
    source.rename(old)
    try:
        staging.rename(source)
    except Exception:
        old.rename(source)
        raise
    shutil.rmtree(old)
