import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from .config import DATABASE_URL

# One autocommit connection per worker thread instead of one per statement. The
# builder runs a small fixed thread pool, so this is bounded without a pool
# dependency that would also have to ship in the offline wheelhouse.
_local = threading.local()
_registry, _registry_guard = [], threading.Lock()


def now():
    return datetime.now(timezone.utc).isoformat()


def _open():
    connection = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True,
                                 connect_timeout=10)
    with _registry_guard:
        _registry.append(connection)
    return connection


def _discard(connection):
    with _registry_guard:
        if connection in _registry:
            _registry.remove(connection)
    try:
        connection.close()
    except Exception:
        pass
    _local.connection = None


@contextmanager
def connection():
    """Reuse this thread's connection; discard failures without replaying writes."""
    existing = getattr(_local, 'connection', None)
    if existing is None or existing.closed:
        if existing is not None:
            _discard(existing)
        existing = _local.connection = _open()
    try:
        yield existing
    except (psycopg.OperationalError, psycopg.InterfaceError):
        _discard(existing)
        raise


def close_all():
    """Called at shutdown; idle server-side connections are not left behind."""
    with _registry_guard:
        connections, _registry[:] = list(_registry), []
    for item in connections:
        try:
            item.close()
        except Exception:
            pass
    _local.connection = None


def _attempt(action):
    # A lost response can happen AFTER COMMIT. Replaying an arbitrary statement
    # or transaction could duplicate a message, revision, event or file operation.
    # Raise the uncertain outcome; the next explicit call gets a fresh connection.
    with connection() as conn:
        return action(conn)


def query(sql, params=(), one=False):
    def action(conn):
        cur = conn.execute(sql, params)
        if cur.description:
            return cur.fetchone() if one else cur.fetchall()
    return _attempt(action)


def batch(statements):
    """Commit related metadata together, or leave none of it behind."""
    def action(conn):
        with conn.transaction():
            for sql, params in statements:
                conn.execute(sql, params)
    return _attempt(action)


def init():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS project_memory (
            project_id TEXT PRIMARY KEY, body TEXT NOT NULL, agent_notes TEXT NOT NULL,
            revision INTEGER NOT NULL, updated_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS feature_plans (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL,
            milestones TEXT NOT NULL, status TEXT NOT NULL, checkpoint TEXT NOT NULL,
            usage TEXT NOT NULL, settings TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        conn.execute("UPDATE feature_plans SET status='needs_review' WHERE status='running'")
        conn.execute('''CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
            repo TEXT, preview_url TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (
            id BIGSERIAL PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            kind TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS events (
            id BIGSERIAL PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
            payload TEXT NOT NULL, created_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS versions (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            label TEXT NOT NULL, digest TEXT NOT NULL, created_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS file_plans (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            prompt TEXT NOT NULL, operations TEXT NOT NULL, status TEXT NOT NULL,
            workspace_digest TEXT NOT NULL, undo_data TEXT, created_at TEXT NOT NULL,
            applied_at TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS recovery_exports (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            filename TEXT NOT NULL, bytes BIGINT NOT NULL, sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS dependency_requests (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
            packages TEXT NOT NULL, reason TEXT NOT NULL, source_digest TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL)''')
        # Idempotent upgrade for existing v0.1 builder databases.
        conn.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS sync_state TEXT")
        conn.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_validation TEXT")
        conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS usage TEXT")
        conn.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'coder'")
        conn.execute("UPDATE runs SET status='interrupted' WHERE status='running'")


def event(run_id, kind, text, **extra):
    query('INSERT INTO events(run_id,payload,created_at) VALUES(%s,%s,%s)',
          (run_id, json.dumps({'kind': kind, 'text': text, **extra}), now()))


def message(project_id, role, content, mode='coder'):
    query('INSERT INTO messages(project_id,role,content,created_at,mode) VALUES(%s,%s,%s,%s,%s)',
          (project_id, role, content, now(), mode))
