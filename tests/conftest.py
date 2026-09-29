"""Builder storage fixtures.

Every test that uses `client` runs twice when a PostgreSQL server is available:
once against the fast SQLite double, and once against the real database the
product ships on, so PostgreSQL-only SQL (BIGSERIAL, ON CONFLICT ... RETURNING,
FOR UPDATE) is actually executed rather than assumed. Point
FOUNDRY_TEST_DATABASE_URL at a scratch database to enable the second pass;
without it the PostgreSQL pass is skipped, not silently dropped.
"""
import os
import sqlite3
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app import config, db, main

# The double's schema, kept here so tests/test_postgres.py can diff it against
# the schema db.init() actually builds and fail on drift.
SQLITE_SCHEMA = '''
CREATE TABLE projects(id TEXT PRIMARY KEY,name TEXT,created_at TEXT,repo TEXT,preview_url TEXT,
    sync_state TEXT,last_validation TEXT);
CREATE TABLE messages(id INTEGER PRIMARY KEY,project_id TEXT,role TEXT,content TEXT,created_at TEXT,mode TEXT DEFAULT 'coder');
CREATE TABLE runs(id TEXT PRIMARY KEY,project_id TEXT,kind TEXT,status TEXT,created_at TEXT,usage TEXT);
CREATE TABLE events(id INTEGER PRIMARY KEY,run_id TEXT,payload TEXT,created_at TEXT);
CREATE TABLE versions(id TEXT PRIMARY KEY,project_id TEXT,label TEXT,digest TEXT,created_at TEXT);
CREATE TABLE file_plans(id TEXT PRIMARY KEY,project_id TEXT,prompt TEXT,operations TEXT,status TEXT,
    workspace_digest TEXT,undo_data TEXT,created_at TEXT,applied_at TEXT);
CREATE TABLE recovery_exports(id TEXT PRIMARY KEY,project_id TEXT,filename TEXT,bytes INTEGER,
    sha256 TEXT,created_at TEXT);
CREATE TABLE dependency_requests(id TEXT PRIMARY KEY,project_id TEXT,packages TEXT,reason TEXT,
    source_digest TEXT,status TEXT,created_at TEXT);
CREATE TABLE project_memory(project_id TEXT PRIMARY KEY,body TEXT,agent_notes TEXT,revision INTEGER,updated_at TEXT);
CREATE TABLE feature_plans(id TEXT PRIMARY KEY,project_id TEXT,title TEXT,milestones TEXT,status TEXT,
    checkpoint TEXT,usage TEXT,settings TEXT,created_at TEXT,updated_at TEXT);
'''


def postgres_url():
    return os.environ.get('FOUNDRY_TEST_DATABASE_URL', '').strip()


def scoped_url(base, schema):
    joiner = '&' if '?' in base else '?'
    return f'{base}{joiner}options=-c%20search_path%3D{schema}'


@pytest.fixture
def sqlite_storage(tmp_path, monkeypatch):
    store = tmp_path / 'state.sqlite'
    with sqlite3.connect(store) as con:
        con.executescript(SQLITE_SCHEMA)

    def query(sql, params=(), one=False):
        with sqlite3.connect(store, timeout=10) as con:
            con.row_factory = sqlite3.Row
            cur = con.execute(sql.replace('%s', '?'), params)
            if cur.description:
                rows = [dict(r) for r in cur.fetchall()]
                return (rows[0] if rows else None) if one else rows

    def batch(statements):
        with sqlite3.connect(store, timeout=10) as con:
            for sql, params in statements:
                con.execute(sql.replace('%s', '?'), params)
    monkeypatch.setattr(db, 'query', query)
    monkeypatch.setattr(db, 'batch', batch)
    monkeypatch.setattr(db, 'init', lambda: None)
    yield


@pytest.fixture
def postgres_storage(monkeypatch):
    """Real db.query/db.batch against a private schema on a scratch database."""
    import psycopg
    base = postgres_url()
    if not base:
        pytest.skip('Set FOUNDRY_TEST_DATABASE_URL to run the PostgreSQL pass.')
    schema = 'foundry_test_' + uuid.uuid4().hex[:12]
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    monkeypatch.setattr(db, 'DATABASE_URL', scoped_url(base, schema))
    db.close_all()
    db.init()
    try:
        yield schema
    finally:
        db.close_all()
        with psycopg.connect(base, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.fixture(params=['sqlite', 'postgres'])
def client(request, tmp_path, monkeypatch):
    request.getfixturevalue('sqlite_storage' if request.param == 'sqlite' else 'postgres_storage')
    monkeypatch.setattr(config, 'TOKEN', 'test-access-token-' + 'x' * 32)
    monkeypatch.setattr(config, 'PROJECTS', tmp_path / 'projects')
    config.PROJECTS.mkdir()
    # No lifespan: a shared process pool must remain available between tests.
    c = TestClient(main.app, base_url='http://127.0.0.1:8765')
    c.headers['Authorization'] = 'Bearer ' + config.TOKEN
    c.storage_backend = request.param
    yield c
    deadline = time.monotonic() + 5
    while main.active_runs and time.monotonic() < deadline:
        time.sleep(.02)
    assert not main.active_runs


def wait_run(client, response):
    assert response.status_code in {200, 202}, response.text
    run_id = response.json()['run_id']
    for _ in range(250):
        data = client.get('/api/runs/' + run_id).json()
        if data['status'] != 'running':
            return data
        time.sleep(.02)
    raise AssertionError('Job did not finish.')


def make_run(project_id, run_id='a' * 32, kind='build'):
    """Real storage enforces run/event foreign keys, so tests that emit events
    for a synthetic run must register that run first."""
    db.query('INSERT INTO runs(id,project_id,kind,status,created_at) VALUES(%s,%s,%s,%s,%s)',
             (run_id, project_id, kind, 'running', db.now()))
    return run_id
