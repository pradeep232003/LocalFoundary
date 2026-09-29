import json
import threading

import pytest

from app import backups, db, files, sandbox, validation


def source_tree(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    files.write(source, 'backend/app/main.py', 'answer = 42')
    files.write(source, 'frontend/src/App.jsx', 'export default function App(){return null}')
    return source


def test_validation_orders_isolated_tests_before_backup_and_preview_migrations(tmp_path, monkeypatch):
    source = source_tree(tmp_path)
    order, updates = [], []
    monkeypatch.setattr(sandbox, 'source_dir', lambda project_id: source)
    monkeypatch.setattr(sandbox, 'command', lambda *a, **kw: order.append('web-build') or 'ok')
    monkeypatch.setattr(sandbox, 'prepare_test_database', lambda project_id: order.append('test-db'))
    monkeypatch.setattr(sandbox, 'test_command', lambda project_id, *args: order.append(
        'test-migrations' if any(str(arg).endswith('/runtime.py') for arg in args) else 'tests') or 'ok')
    monkeypatch.setattr(backups, 'create', lambda project_id, label: order.append('backup') or {'id': 'safe'})
    monkeypatch.setattr(sandbox, 'apply_migrations', lambda project_id: order.append('preview-migrations'))
    monkeypatch.setattr(sandbox, 'start', lambda project_id: order.append('health') or 'http://127.0.0.1:5000')
    monkeypatch.setattr(db, 'event', lambda *a, **kw: None)
    monkeypatch.setattr(db, 'query', lambda sql, params=(), one=False: updates.append((sql, params)))
    monkeypatch.setattr(db, 'now', lambda: 'now')

    report = validation.run('a' * 32, 'b' * 32, threading.Event())

    assert report['status'] == 'passed'
    assert order == ['web-build', 'test-db', 'test-migrations', 'tests', 'backup',
                     'preview-migrations', 'health']
    stored = json.loads(updates[-1][1][0])
    assert stored['status'] == 'passed' and len(stored['checks']) == 8


def test_failed_tests_never_touch_preview_database(tmp_path, monkeypatch):
    source = source_tree(tmp_path)
    touched = []
    monkeypatch.setattr(sandbox, 'source_dir', lambda project_id: source)
    monkeypatch.setattr(sandbox, 'command', lambda *a, **kw: 'ok')
    monkeypatch.setattr(sandbox, 'prepare_test_database', lambda project_id: None)
    monkeypatch.setattr(sandbox, 'test_command', lambda project_id, *args:
                        (_ for _ in ()).throw(RuntimeError('tests failed')) if 'pytest' in args else 'ok')
    monkeypatch.setattr(backups, 'create', lambda *args: touched.append('backup'))
    monkeypatch.setattr(sandbox, 'apply_migrations', lambda *args: touched.append('migrations'))
    monkeypatch.setattr(sandbox, 'start', lambda *args: touched.append('start'))
    monkeypatch.setattr(db, 'event', lambda *a, **kw: None)
    reports = []
    monkeypatch.setattr(db, 'query', lambda sql, params=(), one=False:
                        reports.append(json.loads(params[0])) if 'last_validation=%s' in sql else None)

    with pytest.raises(validation.ValidationFailed, match='Backend tests failed'):
        validation.run('a' * 32, 'b' * 32, threading.Event())

    assert touched == []
    assert reports[-1]['status'] == 'failed'
