"""Checks that only mean something against a real PostgreSQL server.

These cover the gap the SQLite double cannot: the schema db.init() actually
builds, PostgreSQL-only statements, transaction rollback, foreign keys, and the
per-thread connection reuse added to db.py. All are skipped without
FOUNDRY_TEST_DATABASE_URL.
"""
import re
import sqlite3
import threading

import pytest

from app import db, memory
from conftest import SQLITE_SCHEMA


def columns_from_postgres(schema):
    rows = db.query('''SELECT table_name, column_name FROM information_schema.columns
                       WHERE table_schema=%s ORDER BY table_name, column_name''', (schema,))
    result = {}
    for row in rows:
        result.setdefault(row['table_name'], set()).add(row['column_name'])
    return result


def columns_from_double():
    with sqlite3.connect(':memory:') as con:
        con.executescript(SQLITE_SCHEMA)
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {name: {row[1] for row in con.execute(f'PRAGMA table_info({name})')} for name in names}


def test_double_matches_the_real_schema(postgres_storage):
    """The SQLite double is hand-written. If db.init() gains a table or column and
    the double is not updated, every SQLite-only test silently stops covering it."""
    real, double = columns_from_postgres(postgres_storage), columns_from_double()
    assert set(double) == set(real), 'Tables differ between db.init() and the SQLite double.'
    for table in sorted(real):
        assert double[table] == real[table], f'Columns differ for {table}.'


def test_init_is_idempotent_and_resets_interrupted_work(postgres_storage):
    db.query('''INSERT INTO feature_plans(id,project_id,title,milestones,status,checkpoint,usage,settings,created_at,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
             ('p1', 'x' * 32, 'Plan', '[]', 'running', '{}', '{}', '{}', db.now(), db.now()))
    db.init()
    db.init()
    row = db.query('SELECT status FROM feature_plans WHERE id=%s', ('p1',), one=True)
    assert row['status'] == 'needs_review'


def test_bigserial_and_returning_are_real_statements(postgres_storage):
    db.query('INSERT INTO projects(id,name,created_at) VALUES(%s,%s,%s)', ('a' * 32, 'Demo', db.now()))
    db.message('a' * 32, 'user', 'first')
    db.message('a' * 32, 'user', 'second')
    rows = db.query('SELECT id,content FROM messages ORDER BY id')
    assert [r['content'] for r in rows] == ['first', 'second']
    assert rows[0]['id'] < rows[1]['id'], 'BIGSERIAL must allocate increasing identifiers.'


def test_foreign_keys_reject_orphan_events(postgres_storage):
    import psycopg
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.event('b' * 32, 'status', 'orphan')


def test_batch_rolls_back_as_one_unit(postgres_storage):
    import psycopg
    db.query('INSERT INTO projects(id,name,created_at) VALUES(%s,%s,%s)', ('c' * 32, 'Demo', db.now()))
    statements = [
        ('INSERT INTO versions(id,project_id,label,digest,created_at) VALUES(%s,%s,%s,%s,%s)',
         ('v1', 'c' * 32, 'one', 'digest', db.now())),
        ('INSERT INTO versions(id,project_id,label,digest,created_at) VALUES(%s,%s,%s,%s,%s)',
         ('v2', 'missing-project', 'two', 'digest', db.now())),
    ]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.batch(statements)
    assert db.query('SELECT id FROM versions') == [], 'A failed batch must leave nothing behind.'


def test_memory_revision_conflict_under_concurrent_writers(postgres_storage):
    db.query('INSERT INTO projects(id,name,created_at) VALUES(%s,%s,%s)', ('d' * 32, 'Demo', db.now()))
    start = threading.Barrier(2)
    outcomes = []

    def writer(text):
        start.wait()
        try:
            memory.save('d' * 32, {'requirements': text}, 0)
            outcomes.append('applied')
        except ValueError:
            outcomes.append('rejected')

    threads = [threading.Thread(target=writer, args=(f'Requirement {n}',)) for n in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # Both writers start from revision 0, so ON CONFLICT DO NOTHING RETURNING is
    # the only thing standing between them and a lost update.
    assert outcomes.count('applied') == 1, 'Exactly one writer may create revision 1.'
    assert db.query('SELECT revision FROM project_memory', one=True)['revision'] == 1
    with pytest.raises(ValueError):
        memory.save('d' * 32, {'requirements': 'stale'}, 0)
    memory.save('d' * 32, {'requirements': 'current'}, 1)
    assert db.query('SELECT revision FROM project_memory', one=True)['revision'] == 2


def test_each_thread_reuses_one_connection_and_recovers_from_a_dropped_one(postgres_storage):
    seen = []

    def work():
        db.query('SELECT 1 AS value')
        with db.connection() as conn:
            seen.append(id(conn))
        db.query('SELECT 1 AS value')
        with db.connection() as conn:
            seen.append(id(conn))

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert seen[0] == seen[1], 'A thread should not open a new connection per statement.'

    backend = db.query('SELECT pg_backend_pid() AS pid', one=True)['pid']
    with db.connection() as conn:
        conn.close()
    assert db.query('SELECT pg_backend_pid() AS pid', one=True)['pid'] != backend


def test_search_path_scoping_keeps_tests_off_the_public_schema(postgres_storage):
    assert re.fullmatch(r'foundry_test_[0-9a-f]{12}', postgres_storage)
    tables = db.query('''SELECT table_name FROM information_schema.tables
                         WHERE table_schema='public' AND table_name='projects' ''')
    assert tables == []
