"""Fixed providers and encrypted, leased delivery queue. No network in preview."""
import hashlib
import hmac
import json
import time
import httpx
from fastapi import HTTPException
from cryptography.fernet import Fernet
from .db import now, uid


def client(settings):
    if not settings.online:
        raise HTTPException(503, 'Integrations are disabled in this environment.')
    return httpx.Client(proxy=settings.proxy, trust_env=False, follow_redirects=False,
                        timeout=httpx.Timeout(15, connect=5), limits=httpx.Limits(max_connections=5))


def enqueue(c, settings, kind, payload):
    if not settings.online:
        return None
    identifier = uid()
    encrypted = Fernet(settings.encryption_key.encode()).encrypt(json.dumps(payload, separators=(',', ':')).encode()).decode()
    c.execute('INSERT INTO app_outbox(id,kind,payload,available_at,created_at) VALUES(%s,%s,%s,%s,%s)',
              (identifier, kind, encrypted, now(), now()))
    return identifier


def event(c, settings, name, data):
    if settings.webhook_url and settings.online:
        return enqueue(c, settings, 'webhook', {'type': name, 'data': data})


def deliver(settings, row):
    payload = json.loads(Fernet(settings.encryption_key.encode()).decrypt(row['payload'].encode()))
    with client(settings) as http:
        if row['kind'] == 'email':
            if not settings.resend_key or not settings.email_from:
                raise RuntimeError('email_configuration')
            response = http.post('https://api.resend.com/emails', headers={
                'Authorization': 'Bearer ' + settings.resend_key, 'Idempotency-Key': 'foundry/' + row['id']},
                json={'from': settings.email_from, 'to': [payload['to']], 'subject': payload['subject'], 'text': payload['text']})
        elif row['kind'] == 'webhook':
            body = json.dumps({'id': row['id'], 'created_at': row['created_at'], **payload}, separators=(',', ':'), sort_keys=True).encode()
            timestamp = str(now())
            signature = hmac.new(settings.webhook_secret.encode(), timestamp.encode()+b'.'+body, hashlib.sha256).hexdigest()
            response = http.post(settings.webhook_url, content=body, headers={'Content-Type': 'application/json',
                'X-Foundry-Event': row['id'], 'X-Foundry-Signature': 't=' + timestamp + ',v1=' + signature,
                'Idempotency-Key': row['id']})
        else:
            raise RuntimeError('unknown_delivery_kind')
        if not 200 <= response.status_code < 300:
            # Do not persist provider bodies, URLs, credentials, or email contents.
            raise RuntimeError('provider_http_' + str(response.status_code))


def tick(database, settings):
    stamp = now()
    with database.connect() as c:
        c.execute('INSERT INTO app_worker(id,heartbeat) VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat', ('delivery', stamp))
        c.execute('DELETE FROM app_sessions WHERE expires_at<%s OR last_seen<%s', (stamp, stamp-1800))
        c.execute('DELETE FROM app_tokens WHERE expires_at<%s', (stamp,))
        c.execute('DELETE FROM app_rate_limits WHERE expires_at<%s', (stamp,))
        c.execute('DELETE FROM app_audit WHERE created_at<%s', (stamp-90*86400,))
        c.execute("DELETE FROM app_outbox WHERE status='sent' AND created_at<%s", (stamp-30*86400,))
        c.execute('DELETE FROM app_alerts WHERE created_at<%s', (stamp-30*86400,))
        if not settings.online:
            return False
        lock = '' if c.sqlite else ' FOR UPDATE SKIP LOCKED'
        row = c.one("SELECT * FROM app_outbox WHERE (status='queued' AND available_at<=%s) OR (status='sending' AND lease_until<%s) ORDER BY created_at LIMIT 1" + lock, (stamp, stamp))
        if not row:
            return False
        if row['created_at'] < stamp-23*3600 or row['attempts'] >= 8:
            c.execute("UPDATE app_outbox SET status='dead',last_error='delivery_window_expired' WHERE id=%s", (row['id'],))
            return True
        lease = uid()
        c.execute("UPDATE app_outbox SET status='sending',attempts=attempts+1,lease_until=%s,lease_id=%s WHERE id=%s", (stamp+120, lease, row['id']))
    try:
        deliver(settings, row)
        status, error = 'sent', ''
    except Exception as exc:
        status = 'dead' if row['attempts'] + 1 >= 8 else 'queued'
        # RuntimeError messages are our own bounded error codes; all other exceptions are redacted.
        error = str(exc) if type(exc) is RuntimeError and str(exc).startswith(('provider_http_', 'email_configuration', 'unknown_delivery_kind')) else 'delivery_failed'
    with database.connect() as c:
        c.execute('UPDATE app_outbox SET status=%s,last_error=%s,available_at=%s,lease_until=0 WHERE id=%s AND lease_id=%s',
                  (status, error, stamp+min(3600, 30*2**row['attempts']), row['id'], lease))
    return True


def run_worker():
    import signal
    from .db import Database
    from .settings import Settings
    settings = Settings.from_env()
    database = Database(settings.database_url)
    running = True
    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        try:
            active = tick(database, settings)
        except Exception:
            print(json.dumps({'event': 'worker_error', 'time': now()}), flush=True)
            active = False
        time.sleep(0.2 if active else 2)


if __name__ == '__main__':
    run_worker()
