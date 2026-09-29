"""Small parameterized transaction API; PostgreSQL in every deployed environment."""
from contextlib import contextmanager
import sqlite3
import time
import uuid


def now():
    return int(time.time())


def uid():
    return uuid.uuid4().hex


class Connection:
    def __init__(self, conn, sqlite):
        self.conn, self.sqlite = conn, sqlite

    def execute(self, sql, args=()):
        return self.conn.execute(sql.replace('%s', '?') if self.sqlite else sql, args)

    def one(self, sql, args=()):
        row = self.execute(sql, args).fetchone()
        return dict(row) if row else None

    def all(self, sql, args=()):
        return [dict(row) for row in self.execute(sql, args).fetchall()]

    def lock(self):
        # Serialize account/token changes, including concurrent last-admin changes.
        if not self.sqlite:
            self.execute('SELECT pg_advisory_xact_lock(58175005)')


class Database:
    def __init__(self, url):
        self.url = url.replace('postgresql+psycopg://', 'postgresql://', 1)
        self.sqlite = url.startswith('sqlite:')

    @contextmanager
    def connect(self):
        if self.sqlite:
            conn = sqlite3.connect(self.url.removeprefix('sqlite:'), timeout=20)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('BEGIN IMMEDIATE')
        else:
            import psycopg
            from psycopg.rows import dict_row
            conn = psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5,
                                   options='-c statement_timeout=10000 -c lock_timeout=5000')
        try:
            yield Connection(conn, self.sqlite)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def audit(c, actor, action, target=''):
    c.execute('INSERT INTO app_audit(id,actor,action,target,created_at) VALUES(%s,%s,%s,%s,%s)',
              (uid(), actor, action, target, now()))
