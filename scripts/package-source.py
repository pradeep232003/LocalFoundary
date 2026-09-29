#!/usr/bin/env python3
"""Package the complete source distribution without local state or build outputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ('backend', 'frontend', 'template', 'kits', 'browser', 'protected',
             'mobile', 'release-template', 'scripts', 'tests', 'screenshots')
ROOT_FILES = ('package.json', 'firestore.rules', '.env.example', '.gitignore', '.gitattributes', 'README.md', 'WINDOWS.md',
              'Windows.ps1', 'MOBILE.md', 'ruff.toml', 'CHANGELOG.md', 'VALIDATION.md',
              'PROVIDER-ACCEPTANCE.md')
SKIP_DIRS = {'.git', '.venv', '.data', 'node_modules', 'dist', '__pycache__',
             '.pytest_cache', '.ruff_cache', 'pytest-of-root', 'acceptance-results',
             'benchmark-results', 'mobile-build'}
# These are generated captures, not directory names to exclude elsewhere.
SKIP_PATHS = {'screenshots/ui', 'screenshots/accounts', 'screenshots/diff'}
REQUIRED = (*ROOT_FILES, 'backend/app/main.py', 'frontend/package.json',
            'frontend/package-lock.json', 'template/backend/Dockerfile',
            'template/frontend/package-lock.json', 'kits/accounts/backend/app/auth.py',
            'kits/accounts/backend/app/billing.py', 'kits/accounts/backend/requirements.txt',
            'kits/accounts/backend/migrations/002_accounts.sql', 'kits/accounts/frontend/src/App.jsx',
            'scripts/setup.sh', 'scripts/windows/wsl.py', 'scripts/windows/node_runtime.py',
            'scripts/mobile.py', 'scripts/store-screenshots.mjs',
            'backend/app/mobile_builds.py', 'frontend/src/panels/MobilePanel.jsx',
            'frontend/src/panels/mobile.css', 'protected/test_contracts.py')


def excluded_file(name):
    return ((name.startswith('.env') and name != '.env.example')
            or name == '.DS_Store'
            or name.endswith(('.pyc', '.pyo', '.lfr', '.partial', '.log', '.keystore',
                              '.jks', '.mobileprovision', '.p8', '.p12', '.pem', '.key')))


def source_files(source):
    files = {}
    for name in ROOT_FILES:
        path = source / name
        if not path.is_symlink() and path.is_file():
            files[name] = path
    for name in CODE_DIRS:
        folder = source / name
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('Missing or linked source directory: ' + name)
        for current, dirs, names in os.walk(folder, followlinks=False):
            current = Path(current)
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                             and not (current / d).is_symlink()
                             and (current / d).relative_to(source).as_posix() not in SKIP_PATHS)
            for filename in sorted(names):
                path = current / filename
                if not path.is_symlink() and path.is_file() and not excluded_file(filename):
                    files[path.relative_to(source).as_posix()] = path
    missing = sorted(set(REQUIRED) - files.keys())
    if missing:
        raise ValueError('Missing required source files: ' + ', '.join(missing))
    return files


def evidence_files(evidence, version):
    """Include only this report's referenced logs, never stale logs or temp builds."""
    report_path = evidence / 'acceptance.json'
    report = json.loads(report_path.read_text())
    if report.get('version') != version:
        raise ValueError('Acceptance evidence must match the source version.')
    names = {'acceptance.json', 'ACCEPTANCE.md'}
    for check in report['checks']:
        if 'log' in check:
            if not re.fullmatch(r'[0-9]+[.]log', check['log']):
                raise ValueError('Invalid acceptance log filename.')
            names.add(check['log'])
    files = {}
    for name in sorted(names):
        path = evidence / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or linked acceptance evidence: ' + name)
        files['acceptance-results/' + name] = path
    return files


def build_archive(source, output, evidence=None):
    source, output = source.resolve(), output.resolve()
    files = source_files(source)
    version = json.loads(files['frontend/package.json'].read_text())['version']
    if evidence is not None:
        files.update(evidence_files(evidence.resolve(), version))
    if output in files.values():
        raise ValueError('The output must not overwrite a source file.')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 1, 'version': version, 'files': {}}
    fd, temporary = tempfile.mkstemp(prefix=output.name + '.', suffix='.partial', dir=output.parent)
    os.close(fd)
    temporary = Path(temporary)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, path in sorted(files.items()):
                data = path.read_bytes()
                manifest['files'][name] = hashlib.sha256(data).hexdigest()
                entry = zipfile.ZipInfo('local-foundry/' + name)
                entry.create_system = 3
                entry.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
            archive.writestr('local-foundry/SOURCE-MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Archive integrity check failed.')
            for name, digest in manifest['files'].items():
                if hashlib.sha256(archive.read('local-foundry/' + name)).hexdigest() != digest:
                    raise ValueError('Archive content mismatch: ' + name)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'version': version, 'files': len(files) + 1, 'path': str(output),
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, help='Acceptance report directory for this version')
    args = parser.parse_args()
    print(json.dumps(build_archive(args.source, args.output, args.evidence), indent=2))


if __name__ == '__main__':
    main()
