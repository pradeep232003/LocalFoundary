"""Regression cases for the reviewed prototype defects; no external services."""
import sqlite3

from fastapi.testclient import TestClient

from app import codebase_rag, config, db, files, main, sandbox


def create(client):
    response = client.post('/api/projects', json={'name': 'Regression project'})
    assert response.status_code == 201
    return response.json()['id']


def test_all_sensitive_routes_require_workspace_token(client):
    pid = create(client)
    routes = [('/api/projects', 'GET'), (f'/api/projects/{pid}', 'GET'),
              (f'/api/projects/{pid}/rag/export-db', 'GET'),
              (f'/api/projects/{pid}/build', 'POST'),
              (f'/api/projects/{pid}/mobile/builds', 'POST'),
              (f'/api/projects/{pid}/recovery', 'POST'),
              (f'/api/projects/{pid}/github', 'POST'),
              ('/api/agents/validate-price', 'POST')]
    for path, method in routes:
        response = client.request(method, path, headers={'Authorization': ''})
        assert response.status_code == 401, (method, path, response.text)
        assert 'access-control-allow-origin' not in response.headers
    assert client.get('/api/projects', headers={'Origin': 'https://untrusted.invalid'}).status_code == 403
    assert client.get('/api/projects', headers={'Authorization': 'Bearer forged-profile'}).status_code == 401


def test_source_index_is_real_sqlite_persistent_and_tracks_edits(client, tmp_path):
    pid = create(client)
    source = sandbox.source_dir(pid)
    files.write(source, 'backend/app/search_fixture.py', 'quasar_unique_marker = 42\n')
    response = client.post(f'/api/projects/{pid}/rag/search', json={'query': 'quasar_unique_marker'})
    assert response.status_code == 200
    matches = response.json()['matched_files']
    assert len(matches) == 1 and matches[0]['file_path'] == 'backend/app/search_fixture.py'
    assert response.json()['estimates_only'] is True
    assert client.post(f'/api/projects/{pid}/rag/config', json={'enabled': False}).status_code == 200
    assert codebase_rag.context(pid, 'quasar_unique_marker') == ''
    exported = client.get(f'/api/projects/{pid}/rag/export-db')
    path = tmp_path / 'export.sqlite'
    path.write_bytes(exported.content)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert con.execute('SELECT content FROM source WHERE path=?', ('backend/app/search_fixture.py',)).fetchone()[0] == 'quasar_unique_marker = 42\n'
        assert con.execute('SELECT count(*) FROM queries').fetchone()[0] == 1
    # New connections recover index configuration; no process-local Map is involved.
    assert codebase_rag.status(pid)['enabled'] is False
    files.write(source, 'backend/app/search_fixture.py', 'replacement_unique_marker = 99\n')
    assert not codebase_rag.search(pid, 'quasar_unique_marker')['matched_files']
    assert codebase_rag.search(pid, 'replacement_unique_marker')['matched_files']
    invalid = client.post(f'/api/projects/{pid}/rag/config', json={'embedding_model': 'invented-model'})
    assert invalid.status_code == 400


def test_missing_native_artifact_and_invalid_recovery_do_not_succeed(client):
    pid = create(client)
    history = client.get(f'/api/projects/{pid}/mobile/builds').json()
    assert history == []
    assert client.get(f'/api/projects/{pid}/mobile/builds/' + 'a' * 32 + '/download').status_code != 200
    assert client.post(f'/api/projects/{pid}/mobile/builds', json={'target': 'ipa'}).status_code == 422
    result = client.post('/api/recovery/import', content=b'not an archive', headers={
        'Content-Type': 'application/octet-stream', 'X-Foundry-Recovery-Password': 'long-test-password'})
    assert result.status_code == 400


def test_retailer_checks_fail_closed_without_connector(client):
    for endpoint in ('validate-price', 'validate-deal'):
        response = client.post('/api/agents/' + endpoint, json={
            'url': 'https://does-not-exist.invalid/item', 'expectedPrice': '123.45'})
        assert response.status_code == 501
        assert response.json()['verified'] is False
        assert 'domPrice' not in response.json()


def test_new_http_client_reads_saved_project_and_source(client):
    pid = create(client)
    files.write(sandbox.source_dir(pid), 'backend/app/persisted.py', 'persisted_value = 123\n')
    db.close_all()
    restarted_client = TestClient(main.app, base_url='http://127.0.0.1:8765')
    restarted_client.headers['Authorization'] = 'Bearer ' + config.TOKEN
    assert restarted_client.get(f'/api/projects/{pid}').json()['name'] == 'Regression project'
    assert restarted_client.get(f'/api/projects/{pid}/file', params={'path': 'backend/app/persisted.py'}).json()['content'] == 'persisted_value = 123\n'


def test_source_search_rejects_unsafe_input(client):
    pid = create(client)
    assert client.post(f'/api/projects/{pid}/rag/search', json={'query': 'hello', 'top_k': 500}).status_code == 422
    assert client.post(f'/api/projects/{pid}/rag/config', json={'enabled': 'yes'}).status_code == 400
    # User text is tokenized and parameterized, not evaluated as FTS SQL syntax.
    response = client.post(f'/api/projects/{pid}/rag/search', json={'query': '\"; DROP TABLE source; --'})
    assert response.status_code == 200
    assert client.get(f'/api/projects/{pid}/rag/status').json()['indexed_files'] > 0
