"""Behavioral tests of the starter, with SQLite storage and mocked provider HTTP only.
PostgreSQL/container/live provider acceptance is a separate explicit gate.
"""
import hashlib
import hmac
import importlib
import importlib.util
import io
import json
import runpy
import shutil
import socket
from urllib.parse import urlsplit, urlunsplit
import sqlite3
import sys
import types
import zipfile

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import config, db as builder_db, files, sandbox

kit_path = config.ROOT / 'kits/accounts/backend'
package = types.ModuleType('accounts_kit')
package.__path__ = [str(kit_path / 'app')]
sys.modules['accounts_kit'] = package
application = importlib.import_module('accounts_kit.application')
security = importlib.import_module('accounts_kit.security')
settings_module = importlib.import_module('accounts_kit.settings')
storage = importlib.import_module('accounts_kit.db')
integrations = importlib.import_module('accounts_kit.integrations')
billing_module = importlib.import_module('accounts_kit.billing')


def _maintenance_url(base):
    parsed = urlsplit(base)
    return urlunsplit(parsed._replace(path='/postgres'))


def _create_database(base, name):
    import psycopg
    with psycopg.connect(_maintenance_url(base), autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    return urlunsplit(urlsplit(base)._replace(path='/' + name))


def _drop_database(base, name):
    import psycopg
    with psycopg.connect(_maintenance_url(base), autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(params=['sqlite', 'postgres'])
def accounts(request, tmp_path, monkeypatch):
    # Smaller scrypt cost ONLY in this test fixture. Production parameters are tested separately.
    monkeypatch.setattr(security, 'SCRYPT_N', 16384)
    migration = (kit_path / 'migrations/002_accounts.sql').read_text()
    if request.param == 'postgres':
        # Row locking, SKIP LOCKED leases and advisory locks are no-ops on the
        # double, so the kit is also exercised on the database it ships on.
        import uuid as uuid_module

        import psycopg
        from conftest import postgres_url
        base = postgres_url()
        if not base:
            pytest.skip('Set FOUNDRY_TEST_DATABASE_URL to run the PostgreSQL pass.')
        # The kit pins its own libpq options, so a scratch database is used rather
        # than a search_path that the application would override.
        name = 'accounts_test_' + uuid_module.uuid4().hex[:12]
        url = _create_database(base, name)
        request.addfinalizer(lambda: _drop_database(base, name))
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(migration)
    else:
        path = tmp_path / 'accounts.sqlite'
        with sqlite3.connect(path) as c:
            c.executescript(migration)
        url = 'sqlite:' + str(path)
    settings = settings_module.Settings(database_url=url, env='test', signup=True,
        encryption_key=Fernet.generate_key().decode(), ops_token='test-monitoring-' + 'x'*32)
    app = application.create_app(settings)
    with TestClient(app, base_url='http://testserver') as client:
        client.headers['Origin'] = 'http://testserver'
        yield client, app.state.db, settings


def make_user(database, address='member@example.com', role='member'):
    identifier = storage.uid()
    with database.connect() as c:
        c.execute('INSERT INTO app_users(id,email,password,role,verified,created_at) VALUES(%s,%s,%s,%s,1,%s)',
                  (identifier, address, security.hash_password('correct horse battery staple'), role, storage.now()))
    return identifier


def login(client, address='member@example.com'):
    result = client.post('/api/auth/login', json={'email': address, 'password': 'correct horse battery staple'})
    assert result.status_code == 200, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf']
    return result


def token_from(result):
    return result.json()['preview_link'].split('token=')[1]


def enable_payments(settings):
    settings.online, settings.payment_mode = True, 'test'
    settings.origin = 'https://app.example.com'
    settings.stripe_key = 'sk_test_fixture'
    settings.stripe_webhook_secret = 'whsec_fixture'
    settings.catalog = {'starter': {'name': 'Starter', 'price_id': 'price_fixture', 'amount': 1900, 'currency': 'usd'}}


def signed_event(client, settings, obj, kind='checkout.session.completed', identifier='evt_fixture', stamp=None):
    raw = json.dumps({'id': identifier, 'type': kind, 'livemode': False, 'data': {'object': obj}}, separators=(',', ':')).encode()
    stamp = str(storage.now() if stamp is None else stamp)
    digest = hmac.new(settings.stripe_webhook_secret.encode(), stamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
    return client.post('/api/billing/webhook', content=raw, headers={'stripe-signature': 't='+stamp+',v1='+digest, 'Content-Type': 'application/json'})


def order_fixture(database, user):
    with database.connect() as c:
        c.execute('''INSERT INTO app_orders(id,user_id,request_id,product,price_id,amount,currency,session_id,created_at)
            VALUES('order_fixture',%s,'request_fixture','starter','price_fixture',1900,'usd','cs_fixture',%s)''', (user, storage.now()))
    return {'id': 'cs_fixture', 'mode': 'payment', 'client_reference_id': 'order_fixture', 'amount_total': 1900,
            'currency': 'usd', 'payment_status': 'paid', 'payment_intent': 'pi_fixture'}


def test_production_password_parameters():
    assert security.SCRYPT_N == 131072
    encoded = security.hash_password('correct horse battery staple')
    assert encoded.startswith('scrypt$131072$')
    assert security.verify_password('correct horse battery staple', encoded)
    assert not security.verify_password('incorrect password', encoded)


def test_verification_reset_and_revocation(accounts):
    client, database, _ = accounts
    result = client.post('/api/auth/register', json={'email': 'member@example.com', 'password': 'correct horse battery staple'})
    assert result.status_code == 200
    token = token_from(result)
    assert client.post('/api/auth/login', json={'email': 'member@example.com', 'password': 'correct horse battery staple'}).status_code == 401
    assert client.post('/api/auth/complete/verify', json={'token': token}).status_code == 200
    assert client.post('/api/auth/complete/verify', json={'token': token}).status_code == 400
    response = login(client)
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'samesite=lax' in response.headers['set-cookie'].lower()
    assert response.json()['user']['role'] == 'member'
    cookie = client.cookies.get(security.COOKIE)
    with database.connect() as c:
        assert not c.one('SELECT * FROM app_sessions WHERE hash=%s', (cookie,))
        assert c.one('SELECT * FROM app_sessions WHERE hash=%s', (security.hash_token(cookie),))
    reset = client.post('/api/auth/request-reset', json={'email': 'member@example.com'})
    token = token_from(reset)
    assert client.post('/api/auth/complete/reset', json={'token': token, 'password': 'another unique password'}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/complete/reset', json={'token': token, 'password': 'another unique password'}).status_code == 400


def test_origin_csrf_idle_timeout_and_logout(accounts):
    client, database, _ = accounts
    anonymous = client.get('/api/auth/session')
    assert anonymous.status_code == 200 and anonymous.json() == {'user':None,'csrf':''}
    user = make_user(database)
    assert client.post('/api/auth/login', headers={'Origin': 'https://evil.example'}, json={'email':'member@example.com','password':'correct horse battery staple'}).status_code == 403
    login(client)
    assert client.get('/api/auth/session').json()['user']['id'] == user
    assert client.post('/api/notes', headers={'X-CSRF-Token': 'wrong'}, json={'text': 'no'}).status_code == 403
    assert client.post('/api/notes', headers={'Origin': 'https://evil.example'}, json={'text': 'no'}).status_code == 403
    assert client.post('/api/auth/logout', json={}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    login(client)
    with database.connect() as c:
        c.execute('UPDATE app_sessions SET last_seen=%s WHERE user_id=%s', (storage.now()-1801, user))
    assert client.get('/api/auth/me').status_code == 401


def test_private_records_and_role_permissions(accounts):
    client, database, _ = accounts
    make_user(database)
    make_user(database, 'other@example.com')
    make_user(database, 'viewer@example.com', 'viewer')
    login(client)
    note = client.post('/api/notes', json={'text': 'my private plan'}).json()
    assert client.get('/api/admin/users').status_code == 403
    login(client, 'other@example.com')
    assert client.get('/api/notes').json() == []
    assert client.delete('/api/notes/' + note['id']).status_code == 404
    login(client, 'viewer@example.com')
    assert client.post('/api/notes', json={'text':'blocked'}).status_code == 403
    assert client.post('/api/billing/checkout', json={'product':'starter','request_id':'a'*32}).status_code == 403


def test_last_admin_role_changes_revoke_sessions(accounts):
    client, database, _ = accounts
    admin = make_user(database, 'admin@example.com', 'admin')
    member = make_user(database)
    login(client, 'admin@example.com')
    assert client.patch('/api/admin/users/'+admin, json={'role':'member'}).status_code == 409
    assert client.patch('/api/admin/users/'+admin, json={'role':'admin','active':False}).status_code == 409
    assert client.patch('/api/admin/users/'+member, json={'role':'admin'}).status_code == 200
    assert client.patch('/api/admin/users/'+admin, json={'role':'viewer'}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_invitation_and_disabled_user(accounts):
    client, database, _ = accounts
    make_user(database, 'admin@example.com', 'admin')
    login(client, 'admin@example.com')
    invitation = client.post('/api/admin/invite', json={'email':'new@example.com'})
    assert invitation.status_code == 200
    token = token_from(invitation)
    assert client.post('/api/auth/complete/invite', json={'token':token,'password':'correct horse battery staple'}).status_code == 200
    users = client.get('/api/admin/users').json()
    user = next(x for x in users if x['email'] == 'new@example.com')
    assert user['role'] == 'member'
    assert client.patch('/api/admin/users/'+user['id'], json={'role':'member','active':False}).status_code == 200
    assert client.post('/api/auth/login', json={'email':'new@example.com','password':'correct horse battery staple'}).status_code == 401


def test_rate_limits_commit_on_failed_login(accounts):
    client, database, _ = accounts
    make_user(database)
    for _ in range(8):
        assert client.post('/api/auth/login', json={'email':'member@example.com','password':'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'email':'member@example.com','password':'correct horse battery staple'}).status_code == 429


def test_private_metrics_and_redacted_validation(accounts):
    client, database, settings = accounts
    assert client.get('/ops/metrics').status_code == 401
    make_user(database, 'admin@example.com', 'admin')
    login(client, 'admin@example.com')
    result = client.post('/api/auth/login', json={'email':'x','password':'very-secret-password'*20})
    assert result.status_code == 422 and 'very-secret' not in result.text
    assert client.post('/api/notes', content=b'x'*65537).status_code == 413
    summary = client.get('/api/admin/ops').json()
    assert summary['metrics'] and summary['audit']
    assert 'password' not in json.dumps(summary)
    metrics = client.get('/ops/metrics', headers={'Authorization': 'Bearer '+settings.ops_token})
    assert metrics.status_code == 200 and 'foundry_http_requests_total' in metrics.text


def test_preview_payments_do_not_contact_provider(accounts, monkeypatch):
    client, database, settings = accounts
    make_user(database)
    login(client)
    monkeypatch.setattr(integrations, 'client', lambda _: pytest.fail('Unexpected network attempt'))
    assert client.post('/api/billing/checkout', json={'product':'starter','request_id':'a'*32}).status_code == 503
    assert client.post('/api/billing/webhook', content=b'{}').status_code == 503


def test_checkout_retries_use_persisted_idempotency_and_server_prices(accounts, monkeypatch):
    client, database, settings = accounts
    make_user(database)
    login(client)
    enable_payments(settings)
    requests = []
    def provider(request):
        requests.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'active':True,'type':'one_time','unit_amount':1900,'currency':'usd','livemode':False})
        if len([r for r in requests if r.method == 'POST']) == 1:
            return httpx.Response(500, json={'error':'provider private detail'})
        return httpx.Response(200, json={'id':'cs_fixture','url':'https://checkout.stripe.com/c/pay/cs_fixture'})
    monkeypatch.setattr(integrations, 'client', lambda _: httpx.Client(transport=httpx.MockTransport(provider)))
    body = {'product':'starter','request_id':'a'*32, 'amount':1, 'success_url':'https://evil.example'}
    assert client.post('/api/billing/checkout', json=body).status_code == 502
    result = client.post('/api/billing/checkout', json=body)
    assert result.status_code == 200
    assert client.post('/api/billing/checkout', json=body).json() == result.json()
    posts = [r for r in requests if r.method == 'POST']
    assert len(posts) == 2 and posts[0].headers['idempotency-key'] == posts[1].headers['idempotency-key']
    assert b'evil.example' not in posts[0].content and b'price_fixture' in posts[0].content
    assert client.get('/api/billing/orders').json()[0]['status'] == 'pending'


def test_signed_payment_deduplication_refunds_and_no_downgrade(accounts):
    client, database, settings = accounts
    user = make_user(database)
    enable_payments(settings)
    settings.webhook_url = 'https://receiver.example.com/events'
    settings.webhook_secret = 'signing-'+'x'*40
    obj = order_fixture(database, user)
    assert signed_event(client, settings, obj).status_code == 200
    assert signed_event(client, settings, obj).json()['duplicate'] is True
    assert signed_event(client, settings, obj, 'checkout.session.expired', 'evt_expired').status_code == 200
    with database.connect() as c:
        assert c.one('SELECT status FROM app_orders')['status'] == 'paid'
        assert c.one('SELECT COUNT(*) AS n FROM app_outbox')['n'] == 1
    refund = {'payment_intent':'pi_fixture','amount_refunded':500,'currency':'usd'}
    assert signed_event(client, settings, refund, 'charge.refunded', 'evt_refund').status_code == 200
    refund['amount_refunded'] = 100
    assert signed_event(client, settings, refund, 'charge.refunded', 'evt_older_refund').status_code == 200
    assert signed_event(client, settings, obj, identifier='evt_paid_again').status_code == 200
    with database.connect() as c:
        order = c.one('SELECT * FROM app_orders')
        assert order['status'] == 'partially_refunded' and order['refunded'] == 500


@pytest.mark.parametrize('field,value', [('amount_total',1),('currency','eur'),('id','cs_wrong'),('mode','subscription'),('payment_intent',None)])
def test_signed_but_mismatched_payment_cannot_fulfill(accounts, field, value):
    client, database, settings = accounts
    enable_payments(settings)
    obj = order_fixture(database, make_user(database))
    obj[field] = value
    assert signed_event(client, settings, obj).status_code == 400
    with database.connect() as c:
        assert c.one('SELECT status FROM app_orders')['status'] == 'pending'
        assert c.one('SELECT COUNT(*) AS n FROM app_stripe_events')['n'] == 0


def test_webhook_signatures_expiry_and_pending_async_payment(accounts):
    client, database, settings = accounts
    enable_payments(settings)
    obj = order_fixture(database, make_user(database))
    assert client.post('/api/billing/webhook', content=b'{}', headers={'stripe-signature':'invalid'}).status_code == 400
    assert signed_event(client, settings, obj, stamp=storage.now()-301).status_code == 400
    assert signed_event(client, settings, obj, stamp=storage.now()+301).status_code == 400
    obj['payment_status'] = 'unpaid'
    assert signed_event(client, settings, obj).status_code == 200
    with database.connect() as c:
        assert c.one('SELECT status FROM app_orders')['status'] == 'pending'
    obj['payment_status'] = 'paid'
    assert signed_event(client, settings, obj, 'checkout.session.async_payment_succeeded', 'evt_async').status_code == 200


def test_outbox_encryption_retry_leases_and_idempotency(accounts, monkeypatch):
    _, database, settings = accounts
    settings.online = True
    settings.resend_key = 're_fixture'
    settings.email_from = 'sender@example.com'
    with database.connect() as c:
        identifier = integrations.enqueue(c, settings, 'email', {'to':'recipient@example.com','subject':'Test','text':'sensitive-token-link'})
        row = c.one('SELECT * FROM app_outbox')
        assert 'sensitive-token' not in row['payload'] and 'recipient' not in row['payload']
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, json={})
    monkeypatch.setattr(integrations, 'client', lambda _: httpx.Client(transport=httpx.MockTransport(provider)))
    assert integrations.tick(database, settings)
    with database.connect() as c:
        row = c.one('SELECT * FROM app_outbox')
        assert row['status'] == 'queued' and row['attempts'] == 1 and row['last_error'] == 'provider_http_503'
    assert not integrations.tick(database, settings)
    with database.connect() as c:
        c.execute("UPDATE app_outbox SET status='sending',lease_until=%s", (storage.now()-1,))
    assert integrations.tick(database, settings)
    with database.connect() as c:
        assert c.one('SELECT * FROM app_outbox')['status'] == 'sent'
    assert calls[0].headers['idempotency-key'] == calls[1].headers['idempotency-key'] == 'foundry/'+identifier


def test_outbox_expired_delivery_does_not_send(accounts, monkeypatch):
    _, database, settings = accounts
    settings.online = True
    with database.connect() as c:
        integrations.enqueue(c, settings, 'email', {'to':'x@example.com'})
        c.execute('UPDATE app_outbox SET created_at=%s', (storage.now()-24*3600,))
    monkeypatch.setattr(integrations, 'deliver', lambda *args: pytest.fail('Expired delivery sent'))
    assert integrations.tick(database, settings)
    with database.connect() as c:
        assert c.one('SELECT status FROM app_outbox')['status'] == 'dead'


def test_outgoing_webhook_body_signature(accounts, monkeypatch):
    _, database, settings = accounts
    settings.online = True
    settings.webhook_url, settings.webhook_secret = 'https://receiver.example.com/events', 'fixture-'+'x'*40
    with database.connect() as c:
        integrations.event(c, settings, 'order.paid', {'order_id':'test'})
    def provider(request):
        stamp, digest = request.headers['x-foundry-signature'].split(',')
        expected = hmac.new(settings.webhook_secret.encode(), stamp[2:].encode()+b'.'+request.content, hashlib.sha256).hexdigest()
        assert digest == 'v1='+expected
        assert json.loads(request.content)['id'] == request.headers['idempotency-key']
        return httpx.Response(200)
    monkeypatch.setattr(integrations, 'client', lambda _: httpx.Client(transport=httpx.MockTransport(provider)))
    assert integrations.tick(database, settings)


def test_production_secrets_origin_and_secure_cookie(accounts):
    client, database, settings = accounts
    make_user(database)
    settings.env, settings.origin = 'production', 'https://app.example.com'
    client.headers['Origin'] = settings.origin
    response = login(client)
    assert 'secure' in response.headers['set-cookie'].lower()
    assert response.headers['set-cookie'].startswith('__Host-foundry_session=')
    settings.online = True
    settings.resend_key, settings.email_from = 're_fixture', 'sender@example.com'
    reset = client.post('/api/auth/request-reset', json={'email':'member@example.com'})
    assert reset.status_code == 200 and 'preview_link' not in reset.json()
    with database.connect() as c:
        assert c.one('SELECT kind FROM app_outbox')['kind'] == 'email'


def test_configuration_fails_closed():
    with pytest.raises(ValueError, match='SQLite'):
        settings_module.Settings(database_url='sqlite:/tmp/not-production', env='production').validate()
    with pytest.raises(ValueError, match='offline'):
        settings_module.Settings(database_url='postgresql://unused', online=True).validate()
    with pytest.raises(ValueError, match='HTTPS'):
        settings_module.Settings(database_url='postgresql://unused', env='production', origin='http://app.example.com').validate()


def load_proxy():
    spec = importlib.util.spec_from_file_location('test_egress_proxy', config.ROOT/'release-template/egress/proxy.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('ip', ['127.0.0.1','10.0.0.1','169.254.169.254','::1','fc00::1','224.0.0.1','0.0.0.0'])
def test_egress_blocks_private_metadata_and_multicast(monkeypatch, ip):
    proxy = load_proxy()
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip,443))])
    with pytest.raises(ValueError, match='Nonpublic'):
        proxy.public_addresses('receiver.example.com')


def test_egress_exact_hostnames_and_resolved_addresses(monkeypatch):
    proxy = load_proxy()
    assert proxy.allowed_hosts('api.stripe.com,api.resend.com') == {'api.stripe.com','api.resend.com'}
    for host in ['*.example.com','127.0.0.1','example.com:443','user@example.com','https://example.com']:
        with pytest.raises(ValueError):
            proxy.allowed_hosts(host)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1',443))])
    assert proxy.public_addresses('receiver.example.com') == ['1.1.1.1']


def test_builder_accounts_seed_offline_runtime_and_release(client):
    result = client.post('/api/projects', json={'name':'Protected app','profile':'accounts'})
    assert result.status_code == 201, result.text
    identifier = result.json()['id']
    source = sandbox.source_dir(identifier)
    assert client.get('/api/projects/'+identifier).json()['profile'] == 'accounts'
    sandbox.argv(identifier, 'config')
    runtime = json.loads((sandbox.project_dir(identifier)/'runtime.json').read_text())
    assert runtime['services']['api']['environment']['PAYMENT_MODE'] == 'off'
    assert runtime['services']['api']['environment']['ENABLE_INTEGRATIONS'] == 'false'
    assert runtime['networks']['app']['internal']
    assert runtime['services']['api']['image'].startswith('local-foundry-api:deps4-')
    digest = files.digest(source)
    report = {'status':'passed','source_digest':digest,'gate_version':6,'browser_checks':True,
              'checks':[{'name':name,'status':'passed'} for name in ('Protected security contracts','Authenticated user journeys')]}
    builder_db.query('UPDATE projects SET last_validation=%s WHERE id=%s', (json.dumps(report),identifier))
    result = client.post('/api/projects/'+identifier+'/release', json={'source_digest':digest})
    assert result.status_code == 200, result.text
    import yaml
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        compose = yaml.safe_load(archive.read('compose.yaml'))
        assert compose['services']['worker']['environment'] == compose['services']['api']['environment']
        assert compose['services']['api']['networks'] == ['private']
        assert compose['services']['worker']['networks'] == ['private']
        online = yaml.safe_load(archive.read('compose.online.yaml'))
        assert online['services']['egress']['networks'] == ['private','outbound']
        assert 'networks' not in online['services']['api']
        assert b'FOUNDRY_API_IMAGE' not in archive.read('egress/Dockerfile')
        assert 'configure-deployment.py' in archive.namelist()
        assert '.env' not in archive.namelist() and '.secrets/ops-token' not in archive.namelist()
        assert json.loads(archive.read('release.json'))['profile'] == 'accounts'


def test_public_configuration_is_private_and_does_not_overwrite(tmp_path, monkeypatch, capsys):
    for name in ('configure-release.py','configure-deployment.py'):
        shutil.copy2(config.ROOT/'release-template'/name, tmp_path/name)
    (tmp_path/'backend').mkdir()
    (tmp_path/'backend/foundry.json').write_text('{"profile":"accounts","version":"0.5.0"}')
    runpy.run_path(str(tmp_path/'configure-release.py'), run_name='__main__')
    monkeypatch.setattr(sys, 'argv', ['configure-deployment.py','--domain','app.example.com','--acme-email','owner@example.com'])
    runpy.run_path(str(tmp_path/'configure-deployment.py'), run_name='__main__')
    settings = dict(line.split('=',1) for line in (tmp_path/'.env').read_text().splitlines())
    assert settings['PUBLIC_ORIGIN'] == 'https://app.example.com'
    assert settings['APP_ENV'] == 'production' and settings['ENABLE_INTEGRATIONS'] == 'false'
    assert settings['PAYMENT_MODE'] == 'off' and settings['ALLOW_SIGNUP'] == 'false'
    assert (tmp_path/'.env').stat().st_mode & 0o777 == 0o600
    assert (tmp_path/'.secrets').stat().st_mode & 0o777 == 0o700
    assert (tmp_path/'.secrets/ops-token').stat().st_mode & 0o777 == 0o444
    assert (tmp_path/'.secrets/ops-token').read_text() == settings['OPS_TOKEN']
    assert settings['OPS_TOKEN'] not in capsys.readouterr().out
    before = (tmp_path/'.env').read_bytes()
    with pytest.raises(SystemExit):
        runpy.run_path(str(tmp_path/'configure-deployment.py'), run_name='__main__')
    assert (tmp_path/'.env').read_bytes() == before
