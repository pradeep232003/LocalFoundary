"""Human-approved, manifest-only builds. Model code never runs with download access."""
import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path

from . import config, db, files, sandbox
from .process import run

MANIFESTS = ('frontend/package.json', 'frontend/package-lock.json', 'backend/requirements.txt')


class ApprovalRequired(RuntimeError):
    pass


def validate_packages(packages):
    if not isinstance(packages, list) or not 1 <= len(packages) <= 10:
        raise ValueError('Request between 1 and 10 exact package versions.')
    result, seen = [], set()
    for item in packages:
        if not isinstance(item, dict) or set(item) != {'ecosystem', 'name', 'version'}:
            raise ValueError('Each package needs ecosystem, name, and version.')
        ecosystem, name, version = item['ecosystem'], item['name'], item['version']
        if ecosystem not in {'npm', 'pip'} or not isinstance(name, str) or not isinstance(version, str):
            raise ValueError('Choose npm or pip packages.')
        pattern = r'(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*' if ecosystem == 'npm' else r'[A-Za-z0-9][A-Za-z0-9._-]*'
        if len(name) > 100 or not re.fullmatch(pattern, name):
            raise ValueError('Use a registry package name, not a URL, path, alias, or command.')
        version_pattern = r'\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?' if ecosystem == 'npm' else r'\d+(?:\.\d+){1,3}(?:(?:a|b|rc|\.post)\d+)?'
        if len(version) > 50 or not re.fullmatch(version_pattern, version):
            raise ValueError('Use an exact numeric version; ranges and install options are not allowed.')
        key = ecosystem, re.sub(r'[-_.]+', '-', name.lower())
        if key in seen:
            raise ValueError('A package may appear only once per request.')
        seen.add(key)
        result.append(dict(item))
    return result


def manifests(source):
    """Reject imported executable manifest hooks and preserve the trusted stack."""
    template = config.ROOT / 'template'
    original = json.loads((template / MANIFESTS[0]).read_text())
    package = json.loads(files.read(source, MANIFESTS[0]))
    if not isinstance(package, dict) or set(package) != set(original):
        raise ValueError('Unsupported frontend manifest. Restore the trusted React template.')
    for key in original:
        if key != 'dependencies' and package[key] != original[key]:
            raise ValueError('Build scripts and tooling must match the trusted template.')
    if not isinstance(package['dependencies'], dict):
        raise ValueError('Invalid frontend dependencies.')
    for name, version in package['dependencies'].items():
        if name in original['dependencies']:
            if version != original['dependencies'][name]:
                raise ValueError('Upgrading core React tooling requires a builder upgrade.')
        else:
            validate_packages([{'ecosystem': 'npm', 'name': name, 'version': version}])
    if not original['dependencies'].keys() <= package['dependencies'].keys():
        raise ValueError('Core React dependencies may not be removed.')
    base = [line.strip() for line in (template / MANIFESTS[2]).read_text().splitlines() if line.strip()]
    lines = [line.strip() for line in files.read(source, MANIFESTS[2]).splitlines() if line.strip()]
    if lines[:len(base)] != base:
        raise ValueError('Core Python dependencies must match the trusted template.')
    seen = set(re.split(r'[\[<>=]', line)[0].lower() for line in base)
    for line in lines[len(base):]:
        parts = line.split('==')
        if len(parts) != 2 or parts[0].lower() in seen:
            raise ValueError('Python additions must be unique, exact registry versions.')
        validate_packages([{'ecosystem': 'pip', 'name': parts[0], 'version': parts[1]}])
        seen.add(parts[0].lower())
    return package, lines


def image_tag(kind, data, base):
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:24]
    return f'local-foundry-{kind}:' + ('2' if data == base else 'deps4-' + fingerprint)


def accounts_image():
    lines = [x.strip() for x in (config.ROOT / 'kits/accounts/backend/requirements.txt').read_text().splitlines() if x.strip()]
    base = [x.strip() for x in (config.ROOT / 'template/backend/requirements.txt').read_text().splitlines() if x.strip()]
    return image_tag('api', lines, base)


def image_tags(source):
    package, lines = manifests(source)
    template = config.ROOT / 'template'
    original = json.loads((template / MANIFESTS[0]).read_text())
    base_lines = [x.strip() for x in (template / MANIFESTS[2]).read_text().splitlines() if x.strip()]
    return {'web': image_tag('web', package, original), 'api': image_tag('api', lines, base_lines)}


def listing(project_id):
    rows = db.query('SELECT * FROM dependency_requests WHERE project_id=%s ORDER BY created_at DESC', (project_id,))
    for row in rows:
        row['packages'] = json.loads(row['packages'])
    return rows


def propose(project_id, packages, reason):
    packages = validate_packages(packages)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000 or files.SECRET.search(reason):
        raise ValueError('Explain why these packages are needed, without secrets.')
    request_id = uuid.uuid4().hex
    digest = files.digest(sandbox.source_dir(project_id))
    db.query('''INSERT INTO dependency_requests(id,project_id,packages,reason,source_digest,status,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s)''',
             (request_id, project_id, json.dumps(packages), reason, digest, 'pending', db.now()))
    return {'id': request_id, 'status': 'pending', 'packages': packages,
            'message': 'User approval is required in Packages. No packages were installed.'}


def cached(tag):
    try:
        run(['docker', 'image', 'inspect', tag], timeout=15, output_limit=1000)
        return True
    except (RuntimeError, OSError):
        return False


def apply(project_id, request_id, allow_network=False):
    sandbox.validate_id(request_id)
    row = db.query('SELECT * FROM dependency_requests WHERE id=%s AND project_id=%s', (request_id, project_id), one=True)
    if not row or row['status'] != 'pending':
        raise ValueError('This dependency request is no longer pending.')
    source = sandbox.source_dir(project_id)
    if row['source_digest'] != files.digest(source):
        raise ValueError('Source changed after this request. Ask for a fresh package proposal.')
    packages = validate_packages(json.loads(row['packages']))
    package, lines = manifests(source)
    original_package = json.loads((config.ROOT / 'template' / MANIFESTS[0]).read_text())
    python_core = {re.split(r'[\[<>=]', x)[0].lower() for x in
                   (config.ROOT / 'template' / MANIFESTS[2]).read_text().splitlines() if x.strip()}
    for item in packages:
        if item['ecosystem'] == 'npm':
            if item['name'] in original_package['dependencies'] or item['name'] in original_package['devDependencies']:
                raise ValueError('Core framework/tooling upgrades require a builder upgrade.')
            package['dependencies'][item['name']] = item['version']
        else:
            if item['name'].lower() in python_core:
                raise ValueError('Core Python upgrades require a builder upgrade.')
            lines = [x for x in lines if x.split('==')[0].lower() != item['name'].lower()]
            lines.append(item['name'] + '==' + item['version'])
    content = files.export(source)
    content[MANIFESTS[0]] = json.dumps(package, indent=2) + '\n'
    content[MANIFESTS[2]] = '\n'.join(lines) + '\n'
    # A temporary context holds ONLY validated manifests and builder-owned runtime files.
    # No app code, credentials, docker socket, or user folders are sent to networked builds.
    with tempfile.TemporaryDirectory(prefix='foundry-deps-', dir=config.DATA) as directory:
        context = Path(directory)
        (context / 'frontend').mkdir()
        (context / 'backend').mkdir()
        for path in (MANIFESTS[0], MANIFESTS[2]):
            (context / path).write_text(content[path])
        tags = image_tags(context)
        needed = [service for service, tag in tags.items() if not cached(tag)]
        if needed and (config.OFFLINE_ONLY or not allow_network):
            raise ValueError('These runtime images are not cached. Install while connected with explicit network approval; offline mode blocks downloads.')
        for service in needed:
            folder = context / ('frontend' if service == 'web' else 'backend')
            if service == 'web':
                # No shell interpolation from packages; npm never executes lifecycle scripts.
                dockerfile = ('FROM local-foundry-web:2\nUSER 0:0\nWORKDIR /app\n'
                    'COPY package.json ./\nRUN npm install --package-lock-only --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org '
                    '&& npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org\nUSER 1000:1000\n')
            else:
                dockerfile = ('FROM local-foundry-api:2\nUSER 0:0\nCOPY requirements.txt /app/requirements.txt\n'
                    'RUN pip install --no-cache-dir --only-binary=:all: --index-url https://pypi.org/simple -r /app/requirements.txt '
                    '&& pip check\nUSER 1000:1000\n')
            (folder / 'Dockerfile').write_text(dockerfile)
            run(['docker', 'build', '--pull=false', '-t', tags[service], str(folder)], timeout=600)
        # Extract the resolved npm lockfile from the approved image, not an editable project Dockerfile.
        lock = run(['docker', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges:true', '--entrypoint=cat', tags['web'], '/app/package-lock.json'],
                   timeout=30, output_limit=files.MAX_FILE + 1)
        json.loads(lock)
        content[MANIFESTS[1]] = lock
        python_lock = run(['docker', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cap-drop=ALL',
                           '--security-opt=no-new-privileges:true', '--entrypoint=python', tags['api'], '-m', 'pip', 'freeze'],
                          timeout=30, output_limit=files.MAX_FILE + 1)
        if any(not re.fullmatch(r'[A-Za-z0-9._-]+==[A-Za-z0-9.+!-]+', line) for line in python_lock.splitlines() if line):
            raise ValueError('Runtime contained a non-registry Python dependency. Source was not changed.')
        content['backend/requirements-lock.txt'] = python_lock
        if row['source_digest'] != files.digest(source):
            raise ValueError('Source changed during dependency preparation. Nothing was applied.')
        # files.restore validates and atomically swaps the entire source tree.
        staged = context / 'snapshot'
        staged.mkdir()
        (staged / 'files.json').write_text(json.dumps(content))
        sandbox.stop(project_id)
        files.restore(source, staged)
    db.batch([
        ('UPDATE dependency_requests SET status=%s WHERE id=%s', ('applied', request_id)),
        ('UPDATE projects SET last_validation=NULL,preview_url=NULL WHERE id=%s', (project_id,))])
    return {'images': tags, 'message': 'Dependencies installed. Continue the build to validate the updated app.'}
