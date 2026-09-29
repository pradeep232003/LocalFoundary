import io
import json
import threading
import zipfile

import pytest

from app import agent, backups, db, files, main, providers, sandbox, specialists, usage, validation
from conftest import wait_run


def test_bearer_origin_and_host_boundaries(client):
    assert client.get('/api/config', headers={'Authorization': ''}).status_code == 401
    assert client.get('/api/config', headers={'Origin': 'http://127.0.0.1:5173'}).status_code == 403
    assert client.get('/api/config', headers={'Host': 'attacker.example'}).status_code == 400
    assert client.get('/api/config', headers={'Origin': 'http://127.0.0.1:8765'}).status_code == 200


def test_template_create_download_preview_and_source_restore(client, monkeypatch):
    response = client.post('/api/projects', json={'name': 'Notebook'})
    assert response.status_code == 201
    project_id = response.json()['id']
    detail = client.get('/api/projects/' + project_id).json()
    version = detail['versions'][0]['id']
    download = client.get(f'/api/projects/{project_id}/download')
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = archive.namelist()
        assert 'frontend/package-lock.json' in names
        assert 'compose.json' in names and 'backend/app/main.py' in names
        assert '.env' not in names
    monkeypatch.setattr(sandbox, 'start', lambda pid: 'http://127.0.0.1:52341')
    monkeypatch.setattr(sandbox, 'apply_migrations', lambda pid: 'migrations current')
    monkeypatch.setattr(backups, 'create', lambda pid, label: {'id': 'd' * 32, 'label': label})
    stopped = []
    monkeypatch.setattr(sandbox, 'stop', lambda pid: stopped.append(pid))
    result = wait_run(client, client.post(f'/api/projects/{project_id}/preview/start'))
    assert result['status'] == 'completed'
    assert client.get('/api/projects/' + project_id).json()['preview_url'].endswith('52341')
    files.write(sandbox.source_dir(project_id), 'frontend/src/App.jsx', '// changed')
    result = wait_run(client, client.post(f'/api/projects/{project_id}/restore/{version}'))
    assert result['status'] == 'completed'
    assert stopped == [project_id]
    assert 'function App' in files.read(sandbox.source_dir(project_id), 'frontend/src/App.jsx')


def test_agent_edits_actual_file_and_saves_versions(client, monkeypatch):
    project_id = client.post('/api/projects', json={'name': 'Builder test'}).json()['id']
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    calls = []
    def ask(provider, history, max_output_tokens=8000, on_retry=None):
        calls.append(len(history))
        if len(calls) == 1:
            return [], ['Editing your app.'], [{'id': 'call1', 'name': 'write_file',
                'arguments': {'path': 'frontend/src/App.jsx', 'content': 'export default function App(){return <h1>Hello</h1>}'}}], {'input_tokens': 120, 'output_tokens': 30}, False
        assert history[-1]['type'] == 'function_call_output'
        return [], ['Created the page.'], [], {'input_tokens': 180, 'output_tokens': 20}, False
    monkeypatch.setattr(providers, 'ask', ask)
    monkeypatch.setattr(validation, 'run', lambda project_id, run_id, cancelled, **kw: {'status': 'passed'})
    result = wait_run(client, client.post(f'/api/projects/{project_id}/build', json={'prompt': 'Make a hello page', 'provider': 'openai'}))
    assert result['status'] == 'completed'
    assert 'Hello' in files.read(sandbox.source_dir(project_id), 'frontend/src/App.jsx')
    detail = client.get('/api/projects/' + project_id).json()
    assert len(detail['versions']) == 3
    assert detail['messages'][-1]['content'] == 'Created the page.\n\nAll automatic checks passed.'
    assert result['usage']['requests'] == 2


def test_budget_stop_has_distinct_recoverable_status(client, monkeypatch):
    project_id = client.post('/api/projects', json={'name': 'Bounded build'}).json()['id']
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(agent, 'build', lambda *a, **kw: (_ for _ in ()).throw(
        usage.BudgetExceeded('Build budget reached. Saved edits remain available.')))

    result = wait_run(client, client.post(f'/api/projects/{project_id}/build',
        json={'prompt': 'Make a focused change', 'provider': 'openai', 'budget_usd': .25}))

    assert result['status'] == 'budget_exceeded'
    assert any('Saved edits remain available' in event['text'] for event in result['events'])


def test_project_operation_lock_and_cancel(client, monkeypatch):
    project_id = client.post('/api/projects', json={'name': 'Concurrency'}).json()['id']
    gate = threading.Event()
    response = main.launch(project_id, 'build', lambda run_id, cancel: gate.wait(3))
    try:
        assert client.post(f'/api/projects/{project_id}/preview/start').status_code == 409
        assert client.get(f'/api/projects/{project_id}/download').status_code == 409
        assert client.post(f'/api/runs/{response["run_id"]}/cancel').status_code == 200
        assert main.cancellations[response['run_id']].is_set()
    finally:
        gate.set()


def test_github_review_requires_validation_for_exact_source(client, monkeypatch):
    project_id = client.post('/api/projects', json={'name': 'Reviewed export'}).json()['id']
    endpoint = f'/api/projects/{project_id}/github/review'
    assert client.post(endpoint, json={'name': 'reviewed-export'}).status_code == 400

    digest = files.digest(sandbox.source_dir(project_id))
    db.query('UPDATE projects SET last_validation=%s WHERE id=%s',
             (json.dumps({'status': 'passed', 'source_digest': digest, 'checks': []}), project_id))
    monkeypatch.setattr(main.github, 'review', lambda *args, **kwargs: {
        'head': None, 'branch': None, 'source_digest': digest, 'changes': [],
        'conflicts': [], 'preserved_remote_files': 0})
    assert client.post(endpoint, json={'name': 'reviewed-export'}).status_code == 200

    files.write(sandbox.source_dir(project_id), 'frontend/src/App.jsx', '// changed after validation')
    assert client.get(f'/api/projects/{project_id}').json()['last_validation']['status'] == 'stale'
    assert client.post(endpoint, json={'name': 'reviewed-export'}).status_code == 400


def test_document_specialist_is_separate_from_code_validation(client, monkeypatch):
    project_id = client.post('/api/projects', json={'name': 'Local research'}).json()['id']
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(specialists, 'run', lambda *args, **kwargs:
                        ('Answer with [guide.md#chunk-1].', {'requests': 1}, None))
    monkeypatch.setattr(validation, 'run', lambda *args, **kwargs:
                        pytest.fail('Document research must not mutate or validate app source'))

    result = wait_run(client, client.post(f'/api/projects/{project_id}/build', json={
        'prompt': 'What does the guide say?', 'provider': 'openai', 'mode': 'documents'}))

    assert result['status'] == 'completed'
    detail = client.get(f'/api/projects/{project_id}').json()
    assert detail['messages'][-1]['mode'] == 'documents'
    assert '#chunk-1' in detail['messages'][-1]['content']
    assert len(detail['versions']) == 1
