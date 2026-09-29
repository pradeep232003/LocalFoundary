"""Trusted image entrypoint. Applied migrations are immutable and transactional."""
import hashlib
import os
from pathlib import Path
import re
import sys

import psycopg


def migrate(database_url=None, directory=Path('/app/migrations')):
    url = (database_url or os.environ['DATABASE_URL']).replace('postgresql+psycopg://', 'postgresql://')
    paths = sorted(directory.glob('*.sql'))
    if any(not re.fullmatch(r'\d{3,}_[a-z0-9_]+\.sql', p.name) or p.is_symlink() for p in paths):
        raise ValueError('Migration names must be numbered, such as 002_add_status.sql.')
    prefixes = [p.name.split('_')[0] for p in paths]
    if len(prefixes) != len(set(prefixes)):
        raise ValueError('Migration numbers must be unique.')
    with psycopg.connect(url) as connection:
        connection.execute('SELECT pg_advisory_xact_lock(81074629)')
        connection.execute('''CREATE TABLE IF NOT EXISTS _foundry_migrations (
            name TEXT PRIMARY KEY, sha256 TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
        applied = dict(connection.execute('SELECT name,sha256 FROM _foundry_migrations').fetchall())
        missing = set(applied) - {p.name for p in paths}
        if missing:
            raise ValueError('Applied migration files are missing: ' + ', '.join(sorted(missing)))
        for path in paths:
            sql = path.read_text()
            digest = hashlib.sha256(sql.encode()).hexdigest()
            if path.name in applied:
                if applied[path.name] != digest:
                    raise ValueError('Applied migration was edited: ' + path.name + '. Add a new migration instead.')
                continue
            connection.execute(sql, prepare=False)
            connection.execute('INSERT INTO _foundry_migrations(name,sha256) VALUES(%s,%s)', (path.name, digest))
            print('Applied ' + path.name, flush=True)
    print('Database migrations are current.', flush=True)


if __name__ == '__main__':
    migrate()
    if len(sys.argv) < 2 or sys.argv[1] != 'migrate':
        os.execvp('uvicorn', ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000',
                              '--reload', '--reload-dir', '/app/app'])
