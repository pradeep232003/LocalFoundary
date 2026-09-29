"""Builder-owned behavioral contracts. Run against the generated app and real test DB."""
import hashlib
import hmac
import json
import secrets
import time


def exercise(client, database):
    password = secrets.token_urlsafe(24)
    suffix = secrets.token_hex(5)
    users = {}
    for role in ('member', 'viewer', 'admin'):
        email = f'{role}-{suffix}@example.test'
        result = client.post('/api/auth/register', json={'email': email, 'password': password})
        assert result.status_code == 200, 'Registration failed'
        token = result.json()['preview_link'].split('token=')[1]
        assert client.post('/api/auth/complete/verify', json={'token': token}).status_code == 200
        assert client.post('/api/auth/complete/verify', json={'token': token}).status_code == 400, 'Verification token reused'
        with database.connect() as c:
            c.execute('UPDATE app_users SET role=%s WHERE email=%s', (role, email))
            row = c.one('SELECT * FROM app_users WHERE email=%s', (email,))
        assert row['password'] != password and password not in row['password'], 'Password stored in plaintext'
        users[role] = row

    def signin(role):
        client.cookies.clear()
        result = client.post('/api/auth/login', json={'email': users[role]['email'], 'password': password})
        assert result.status_code == 200, 'Sign-in failed'
        cookie = result.headers.get('set-cookie', '').lower()
        assert 'httponly' in cookie and 'samesite=lax' in cookie
        client.headers['X-CSRF-Token'] = result.json()['csrf']
        return result.json()

    client.cookies.clear()
    for path in ('/api/notes', '/api/admin/users', '/api/admin/ops', '/api/billing/orders'):
        assert client.get(path).status_code == 401, 'Anonymous protected read: ' + path
    signin('member')
    assert client.get('/api/admin/users').status_code == 403, 'Member gained admin access'
    assert client.post('/api/notes', json={'text': 'blocked'}, headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.post('/api/notes', json={'text': 'blocked'}, headers={'Origin': 'https://outside.invalid'}).status_code == 403
    note = client.post('/api/notes', json={'text': 'Protected ownership contract'})
    assert note.status_code == 200
    identifier = note.json()['id']
    old_cookie = dict(client.cookies)
    signin('viewer')
    assert identifier not in [row['id'] for row in client.get('/api/notes').json()], 'Cross-user record disclosure'
    assert client.post('/api/notes', json={'text': 'blocked'}).status_code == 403, 'Viewer could write'
    signin('admin')
    assert client.delete('/api/notes/' + identifier).status_code == 404, 'Admin bypassed private ownership'
    assert client.patch('/api/admin/users/' + users['member']['id'], json={'role': 'viewer'}).status_code == 200
    client.cookies.clear()
    client.cookies.update(old_cookie)
    assert client.get('/api/auth/me').status_code == 401, 'Role change did not revoke session'
    signin('viewer')
    old_cookie = dict(client.cookies)
    assert client.post('/api/auth/logout').status_code == 200
    client.cookies.update(old_cookie)
    assert client.get('/api/auth/me').status_code == 401, 'Logout did not revoke session'
    client.cookies.clear()
    reset = client.post('/api/auth/request-reset', json={'email': users['viewer']['email']})
    assert reset.status_code == 200
    token = reset.json()['preview_link'].split('token=')[1]
    replacement = secrets.token_urlsafe(24)
    assert client.post('/api/auth/complete/reset', json={'token': token, 'password': replacement}).status_code == 200
    assert client.post('/api/auth/complete/reset', json={'token': token, 'password': replacement}).status_code == 400
    assert client.post('/api/auth/login', json={'email': users['viewer']['email'], 'password': password}).status_code == 401
    assert client.post('/api/auth/login', json={'email': users['viewer']['email'], 'password': replacement}).status_code == 200
    # Preview integrations are disabled; arbitrary unsigned payment events cannot be accepted.
    assert client.post('/api/billing/webhook', content=b'{}').status_code in (400, 403, 503)
    # Exercise signatures and replay protection without contacting Stripe or enabling a worker.
    settings = client.app.state.settings
    settings.online, settings.payment_mode = True, 'test'
    settings.stripe_webhook_secret = 'whsec_' + secrets.token_hex(24)
    settings.webhook_url = ''
    order_id, event_id = 'order'+suffix, 'evt'+suffix
    with database.connect() as c:
        c.execute('INSERT INTO app_orders(id,user_id,request_id,product,price_id,amount,currency,session_id,created_at) VALUES(%s,%s,%s,%s,%s,1900,%s,%s,%s)',
            (order_id, users['member']['id'], 'request'+suffix, 'starter', 'price_fixture', 'usd', 'cs_'+suffix, int(time.time())))
    obj = {'id':'cs_'+suffix, 'mode':'payment', 'client_reference_id':order_id, 'amount_total':1900,
           'currency':'usd', 'payment_status':'paid', 'payment_intent':'pi_'+suffix}
    def webhook(body, *, identifier=event_id, stamp=None, secret=None):
        raw = json.dumps({'id':identifier, 'type':'checkout.session.completed', 'livemode':False, 'data':{'object':body}}).encode()
        stamp = str(int(time.time()) if stamp is None else stamp)
        signature = hmac.new((secret or settings.stripe_webhook_secret).encode(), stamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return client.post('/api/billing/webhook', content=raw, headers={'stripe-signature':'t='+stamp+',v1='+signature, 'Content-Type':'application/json'})
    assert webhook(obj, secret='wrong').status_code == 400, 'Forged payment signature accepted'
    assert webhook(obj, stamp=int(time.time())-1000).status_code == 400, 'Expired payment signature accepted'
    assert webhook({**obj,'amount_total':1}).status_code == 400, 'Wrong payment amount accepted'
    assert webhook(obj).status_code == 200
    assert webhook(obj).status_code == 200
    with database.connect() as c:
        assert c.one('SELECT status FROM app_orders WHERE id=%s', (order_id,))['status'] == 'paid'
        assert c.one('SELECT count(*) AS n FROM app_stripe_events WHERE id=%s', (event_id,))['n'] == 1
        assert c.one("SELECT count(*) AS n FROM app_audit WHERE action='order.paid' AND target=%s", (order_id,))['n'] == 1, 'Duplicate payment effects'
