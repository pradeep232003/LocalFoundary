"""Browser evidence produced in an isolated, non-root container on the app network."""
import base64
import json
import uuid
from urllib.parse import unquote, urlsplit

from . import db, files, sandbox
from .process import run

IMAGE = 'local-foundry-browser:4'
MAX_IMAGE = 2_000_000


def validate_options(path='/', viewport='desktop', actions=None):
    if not isinstance(path, str) or len(path) > 1000 or not path.startswith('/'):
        raise ValueError('Use a relative preview path beginning with /.')
    decoded = unquote(path)
    if (decoded.startswith('//') or '\\' in decoded or urlsplit(decoded).netloc or
            any(ord(char) < 32 for char in decoded)):
        raise ValueError('Browser navigation cannot leave the app origin.')
    if viewport not in {'desktop', 'mobile'}:
        raise ValueError('Choose a desktop or mobile viewport.')
    actions = [] if actions is None else actions
    if not isinstance(actions, list) or len(actions) > 12:
        raise ValueError('Browser checks support up to 12 bounded actions.')
    for item in actions:
        if not isinstance(item, dict) or set(item) != {'action', 'selector', 'value'}:
            raise ValueError('Each action needs action, selector, and value fields.')
        if item['action'] not in {'click', 'fill', 'visible'}:
            raise ValueError('Only click, fill, and visible checks are supported.')
        if not isinstance(item['selector'], str) or not 1 <= len(item['selector']) <= 300:
            raise ValueError('Use a short CSS or Playwright selector.')
        if not isinstance(item['value'], str) or len(item['value']) > 2000 or files.SECRET.search(item['value']):
            raise ValueError('Browser test values must be short and contain no secrets.')
    return {'path': path, 'viewport': viewport, 'actions': actions}


def folder(project_id):
    root = sandbox.project_dir(project_id) / 'visual'
    root.mkdir(exist_ok=True, mode=0o700)
    if root.is_symlink():
        raise ValueError('Unsafe visual artifact directory.')
    return root


def capture(project_id, path='/', viewport='desktop', actions=None):
    options = validate_options(path, viewport, actions)
    sandbox.start(project_id)
    source_digest = files.digest(sandbox.source_dir(project_id))
    container_name = 'foundry-visual-' + uuid.uuid4().hex
    argv = ['docker', 'run', '--rm', '-i', '--pull=never', '--name', container_name,
            '--network=foundry-' + sandbox.validate_id(project_id) + '_app',
            '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
            '--pids-limit=256', '--memory=2g', '--cpus=2', '--init', '--shm-size=256m',
            '--tmpfs=/tmp:rw,nosuid,size=512m', IMAGE]
    try:
        output = run(argv, input_text=json.dumps(options), timeout=115, output_limit=MAX_IMAGE * 2)
    finally:
        # A timed-out Docker CLI does not guarantee its container was stopped.
        try:
            run(['docker', 'rm', '--force', container_name], timeout=15, output_limit=1000)
        except (OSError, RuntimeError):
            pass
    report = json.loads(output)
    raw = base64.b64decode(report.pop('screenshot'), validate=True)
    if len(raw) > MAX_IMAGE or not raw.startswith(b'\xff\xd8\xff'):
        raise ValueError('Browser returned an invalid screenshot.')
    if files.digest(sandbox.source_dir(project_id)) != source_digest:
        raise ValueError('Source changed during the browser check. Run it again.')
    report['id'] = uuid.uuid4().hex
    report.update(path=path, viewport=viewport, created_at=db.now(), source_digest=source_digest)
    report['status'] = 'passed' if (report.get('status_code') == 200 and
        not report.get('errors') and not report.get('failed_requests') and
        not report.get('horizontal_overflow') and report.get('text', '').strip()) else 'failed'
    root = folder(project_id)
    with (root / (report['id'] + '.jpg')).open('xb') as stream:
        stream.write(raw)
    (root / (report['id'] + '.json')).write_text(json.dumps(report))
    return report


def listing(project_id):
    paths = sorted(folder(project_id).glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)[:20]
    return [json.loads(path.read_text()) for path in paths if not path.is_symlink() and path.stat().st_size < 50000]


def image_path(project_id, artifact_id):
    sandbox.validate_id(artifact_id)
    path = folder(project_id) / (artifact_id + '.jpg')
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_IMAGE:
        raise ValueError('Screenshot not found.')
    return path


def image_data(project_id, artifact_id):
    return base64.b64encode(image_path(project_id, artifact_id).read_bytes()).decode()


def check(project_id):
    reports = [capture(project_id, viewport=viewport) for viewport in ('desktop', 'mobile')]
    failed = [report for report in reports if report['status'] != 'passed']
    if failed:
        raise RuntimeError(json.dumps([{key: value for key, value in report.items() if key != 'text'} for report in failed])[:3000])
    return reports
