import base64
import hashlib
import hmac
import re
import secrets
import threading
from urllib.parse import urlsplit
from fastapi import HTTPException, Request
from .db import now

SCRYPT_N = 131072
COOKIE = 'foundry_session'
PASSWORD_SLOTS = threading.BoundedSemaphore(2)


def cookie_name(settings):
    # The __Host prefix prevents a sibling subdomain from setting this cookie.
    return '__Host-foundry_session' if settings.production else COOKIE


def email(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[A-Za-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}', value):
        raise HTTPException(422, 'Enter a valid email address.')
    return value


def hash_token(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(value):
    if not 12 <= len(value) <= 128:
        raise HTTPException(422, 'Use a password of 12–128 characters.')
    salt = secrets.token_bytes(16)
    with PASSWORD_SLOTS:
        digest = hashlib.scrypt(value.encode(), salt=salt, n=SCRYPT_N, r=8, p=1, maxmem=256*1024*1024)
    return 'scrypt$%d$%s$%s' % (SCRYPT_N, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(value, encoded):
    try:
        algorithm, cost, salt, expected = encoded.split('$')
        if algorithm != 'scrypt' or not 16384 <= int(cost) <= SCRYPT_N or len(value) > 128:
            return False
        with PASSWORD_SLOTS:
            actual = hashlib.scrypt(value.encode(), salt=base64.b64decode(salt), n=int(cost), r=8, p=1, maxmem=256*1024*1024)
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def csrf(token):
    return hmac.new(token.encode(), b'foundry-csrf-v1', hashlib.sha256).hexdigest()


def origin_check(request: Request):
    settings = request.app.state.settings
    origin = request.headers.get('origin', '')
    if settings.production:
        valid = origin == settings.origin
    else:
        u = urlsplit(origin)
        # Exact same-origin plus known preview hosts; never accept arbitrary Origin reflection.
        valid = u.scheme == 'http' and u.hostname in {'127.0.0.1', 'localhost', 'web', 'testserver'} and origin == str(request.base_url).rstrip('/')
    if not valid:
        raise HTTPException(403, 'Request origin was rejected.')


def rate_limit(database, bucket, value, limit=8, seconds=900):
    stamp = now()
    key = hash_token(bucket + ':' + value + ':' + str(stamp // seconds))
    with database.connect() as c:
        row = c.one('''INSERT INTO app_rate_limits(key,count,expires_at) VALUES(%s,1,%s)
            ON CONFLICT(key) DO UPDATE SET count=app_rate_limits.count+1 RETURNING count''', (key, stamp + seconds))
    if row['count'] > limit:
        raise HTTPException(429, 'Too many attempts. Please try again later.', headers={'Retry-After': str(seconds)})


def user_view(user):
    return {key: user[key] for key in ('id', 'email', 'role', 'verified', 'active')}


def current_user(request: Request):
    raw = request.cookies.get(cookie_name(request.app.state.settings), '')
    if not 20 <= len(raw) <= 200:
        raise HTTPException(401, 'Sign in to continue.')
    with request.app.state.db.connect() as c:
        user = c.one('''SELECT u.*,s.expires_at,s.last_seen FROM app_users u JOIN app_sessions s ON u.id=s.user_id
                       WHERE s.hash=%s''', (hash_token(raw),))
        if not user or not user['active'] or not user['verified'] or user['expires_at'] <= now() or user['last_seen'] < now()-1800:
            raise HTTPException(401, 'Your session ended. Sign in again.')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin_check(request)
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), csrf(raw)):
                raise HTTPException(403, 'Refresh the page and try again.')
        c.execute('UPDATE app_sessions SET last_seen=%s WHERE hash=%s', (now(), hash_token(raw)))
    return user


def role(request, *allowed):
    user = current_user(request)
    if user['role'] not in allowed:
        raise HTTPException(403, 'Your role does not allow this action.')
    return user
