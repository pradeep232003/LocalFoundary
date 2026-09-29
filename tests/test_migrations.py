import hashlib
import importlib.util
from pathlib import Path

import pytest


def runtime_module():
    path = Path(__file__).parents[1] / 'template/backend/runtime.py'
    spec = importlib.util.spec_from_file_location('foundry_template_runtime', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Result:
    def __init__(self, rows=()):
        self.rows = rows

    def fetchall(self):
        return list(self.rows)


class Connection:
    def __init__(self, applied):
        self.applied = applied
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None, **options):
        self.calls.append((sql, params, options))
        if sql.startswith('SELECT name,sha256'):
            return Result(self.applied.items())
        return Result()


def test_runner_applies_only_new_numbered_migrations(tmp_path, monkeypatch):
    runtime = runtime_module()
    first = tmp_path / '001_notes.sql'
    second = tmp_path / '002_status.sql'
    first.write_text('CREATE TABLE notes(id bigint);')
    second.write_text('ALTER TABLE notes ADD COLUMN status text;')
    connection = Connection({first.name: hashlib.sha256(first.read_bytes()).hexdigest()})
    monkeypatch.setattr(runtime.psycopg, 'connect', lambda url: connection)

    runtime.migrate('postgresql://test', tmp_path)

    executed = [call[0] for call in connection.calls]
    assert first.read_text() not in executed
    assert second.read_text() in executed
    assert any(sql.startswith('INSERT INTO _foundry_migrations') and params[0] == second.name
               for sql, params, options in connection.calls)


def test_runner_rejects_edited_or_missing_applied_migration(tmp_path, monkeypatch):
    runtime = runtime_module()
    migration = tmp_path / '001_notes.sql'
    migration.write_text('changed')
    monkeypatch.setattr(runtime.psycopg, 'connect', lambda url: Connection({'001_notes.sql': 'old-hash'}))
    with pytest.raises(ValueError, match='was edited'):
        runtime.migrate('postgresql://test', tmp_path)

    migration.unlink()
    with pytest.raises(ValueError, match='missing'):
        runtime.migrate('postgresql://test', tmp_path)


@pytest.mark.parametrize('names', [
    ['notes.sql'],
    ['001_notes.sql', '001_more.sql'],
    ['002_BadName.sql'],
])
def test_runner_rejects_ambiguous_names(tmp_path, monkeypatch, names):
    runtime = runtime_module()
    for name in names:
        (tmp_path / name).write_text('SELECT 1;')
    monkeypatch.setattr(runtime.psycopg, 'connect', lambda url: Connection({}))
    with pytest.raises(ValueError, match='Migration names|unique'):
        runtime.migrate('postgresql://test', tmp_path)
