CREATE TABLE app_users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('admin','member','viewer')),
 verified INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
 created_at BIGINT NOT NULL
);
CREATE TABLE app_sessions (
 hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 expires_at BIGINT NOT NULL, last_seen BIGINT NOT NULL
);
CREATE INDEX app_sessions_user ON app_sessions(user_id);
CREATE TABLE app_tokens (
 hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, expires_at BIGINT NOT NULL
);
CREATE TABLE app_rate_limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at BIGINT NOT NULL);
CREATE TABLE app_audit (id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, created_at BIGINT NOT NULL);
CREATE INDEX app_audit_time ON app_audit(created_at);
CREATE TABLE app_records (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES app_users(id), text TEXT NOT NULL, created_at BIGINT NOT NULL);
CREATE INDEX app_records_owner ON app_records(user_id,created_at);
CREATE TABLE app_orders (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES app_users(id), request_id TEXT NOT NULL,
 product TEXT NOT NULL, price_id TEXT NOT NULL, amount INTEGER NOT NULL, currency TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', session_id TEXT UNIQUE, checkout_url TEXT,
 payment_intent TEXT UNIQUE, refunded INTEGER NOT NULL DEFAULT 0, created_at BIGINT NOT NULL,
 UNIQUE(user_id,request_id)
);
CREATE TABLE app_stripe_events (id TEXT PRIMARY KEY, type TEXT NOT NULL, created_at BIGINT NOT NULL);
CREATE TABLE app_outbox (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
 attempts INTEGER NOT NULL DEFAULT 0, available_at BIGINT NOT NULL, lease_until BIGINT NOT NULL DEFAULT 0,
 lease_id TEXT, last_error TEXT NOT NULL DEFAULT '', created_at BIGINT NOT NULL
);
CREATE INDEX app_outbox_ready ON app_outbox(status,available_at);
CREATE TABLE app_metrics (route TEXT NOT NULL, method TEXT NOT NULL, status INTEGER NOT NULL, count BIGINT NOT NULL, duration_ms BIGINT NOT NULL, PRIMARY KEY(route,method,status));
CREATE TABLE app_alerts (id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, created_at BIGINT NOT NULL);
CREATE TABLE app_worker (id TEXT PRIMARY KEY, heartbeat BIGINT NOT NULL);
