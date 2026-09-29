import secrets
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from . import security as sec
from .db import audit, now, uid

router = APIRouter(prefix='/api')


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class EmailInput(BaseModel):
    email: str = Field(max_length=254)


class TokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(default='', max_length=128)


class RoleInput(BaseModel):
    role: str
    active: bool = True


def send_token(request, c, user, kind):
    from .integrations import enqueue
    settings = request.app.state.settings
    token = secrets.token_urlsafe(32)
    c.execute('DELETE FROM app_tokens WHERE user_id=%s AND kind=%s', (user['id'], kind))
    c.execute('INSERT INTO app_tokens(hash,user_id,kind,expires_at) VALUES(%s,%s,%s,%s)',
              (sec.hash_token(token), user['id'], kind, now() + 1800))
    fragment = '#action=' + kind + '&token=' + token
    if settings.production:
        if not (settings.online and settings.resend_key and settings.email_from):
            raise HTTPException(503, 'Email delivery is not configured.')
        enqueue(c, settings, 'email', {'to': user['email'], 'subject': 'Complete your account request',
            'text': 'Open this link within 30 minutes: ' + settings.origin + '/' + fragment})
        return {}
    # Preview/test only; raw tokens never enter audit logs or production responses.
    return {'preview_link': '/' + fragment}


@router.post('/auth/register')
def register(body: Credentials, request: Request):
    sec.origin_check(request)
    settings, database = request.app.state.settings, request.app.state.db
    if not settings.signup:
        raise HTTPException(403, 'Registration is by invitation.')
    address = sec.email(body.email)
    sec.rate_limit(database, 'register', request.client.host, 15)
    password = sec.hash_password(body.password)
    result = {'message': 'If registration is available, check your email to continue.'}
    with database.connect() as c:
        c.lock()
        user = c.one('SELECT * FROM app_users WHERE email=%s', (address,))
        if not user:
            user = {'id': uid(), 'email': address}
            c.execute('INSERT INTO app_users(id,email,password,role,created_at) VALUES(%s,%s,%s,%s,%s)',
                      (user['id'], address, password, 'member', now()))
            audit(c, user['id'], 'account.register')
            result.update(send_token(request, c, user, 'verify'))
    return result


@router.post('/auth/login')
def login(body: Credentials, request: Request, response: Response):
    sec.origin_check(request)
    database = request.app.state.db
    address = sec.email(body.email)
    sec.rate_limit(database, 'login-account', address)
    sec.rate_limit(database, 'login-ip', request.client.host, 80)
    with database.connect() as c:
        user = c.one('SELECT * FROM app_users WHERE email=%s', (address,))
    encoded = user['password'] if user else request.app.state.dummy_password
    valid = sec.verify_password(body.password, encoded)
    if not user or not valid or not user['active'] or not user['verified']:
        with database.connect() as c:
            audit(c, user['id'] if user else 'anonymous', 'login.failed')
        raise HTTPException(401, 'Sign-in failed. Check your credentials and email verification.')
    raw = secrets.token_urlsafe(32)
    with database.connect() as c:
        c.lock()
        # Recheck state in the same lock used for password resets and role changes.
        latest = c.one('SELECT * FROM app_users WHERE id=%s', (user['id'],))
        if not latest['active'] or latest['password'] != encoded:
            raise HTTPException(401, 'Sign-in failed.')
        c.execute('INSERT INTO app_sessions(hash,user_id,expires_at,last_seen) VALUES(%s,%s,%s,%s)',
                  (sec.hash_token(raw), user['id'], now()+43200, now()))
        audit(c, user['id'], 'login.succeeded')
    response.set_cookie(sec.cookie_name(request.app.state.settings), raw, max_age=43200, httponly=True, secure=request.app.state.settings.production,
                        samesite='lax', path='/')
    return {'user': sec.user_view(latest), 'csrf': sec.csrf(raw)}


@router.get('/auth/me')
def me(request: Request):
    return {'user': sec.user_view(sec.current_user(request)), 'csrf': sec.csrf(request.cookies[sec.cookie_name(request.app.state.settings)])}


@router.get('/auth/session')
def session(request: Request):
    # Anonymous is a normal boot state, not a failed browser request.
    try:
        return me(request)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        return {'user': None, 'csrf': ''}


@router.post('/auth/logout')
def logout(request: Request, response: Response):
    user = sec.current_user(request)
    with request.app.state.db.connect() as c:
        c.execute('DELETE FROM app_sessions WHERE hash=%s', (sec.hash_token(request.cookies[sec.cookie_name(request.app.state.settings)]),))
        audit(c, user['id'], 'logout')
    response.delete_cookie(sec.cookie_name(request.app.state.settings), path='/', secure=request.app.state.settings.production, httponly=True, samesite='lax')
    return {'ok': True}


@router.post('/auth/request-reset')
def request_reset(body: EmailInput, request: Request):
    sec.origin_check(request)
    address = sec.email(body.email)
    sec.rate_limit(request.app.state.db, 'reset-account', address, 3)
    sec.rate_limit(request.app.state.db, 'reset-ip', request.client.host, 20)
    result = {'message': 'If an active account exists, check your email for a reset link.'}
    with request.app.state.db.connect() as c:
        c.lock()
        user = c.one('SELECT * FROM app_users WHERE email=%s AND active=1', (address,))
        if user:
            result.update(send_token(request, c, user, 'reset'))
    return result


@router.post('/auth/complete/{kind}')
def complete(kind: str, body: TokenInput, request: Request):
    sec.origin_check(request)
    if kind not in {'verify', 'reset', 'invite'}:
        raise HTTPException(404, 'Unknown account action.')
    sec.rate_limit(request.app.state.db, 'complete', request.client.host, 30)
    password = sec.hash_password(body.password) if kind in {'reset', 'invite'} else None
    with request.app.state.db.connect() as c:
        c.lock()
        token = c.one('SELECT * FROM app_tokens WHERE hash=%s AND kind=%s AND expires_at>%s',
                      (sec.hash_token(body.token), kind, now()))
        if not token:
            raise HTTPException(400, 'This link expired or was already used.')
        if password:
            c.execute('UPDATE app_users SET password=%s,verified=1 WHERE id=%s', (password, token['user_id']))
        else:
            c.execute('UPDATE app_users SET verified=1 WHERE id=%s', (token['user_id'],))
        c.execute('DELETE FROM app_tokens WHERE user_id=%s', (token['user_id'],))
        c.execute('DELETE FROM app_sessions WHERE user_id=%s', (token['user_id'],))
        audit(c, token['user_id'], 'account.' + kind)
    return {'message': 'Account updated. You can now sign in.'}


@router.get('/admin/users')
def users(request: Request):
    sec.role(request, 'admin')
    with request.app.state.db.connect() as c:
        return c.all('SELECT id,email,role,verified,active FROM app_users ORDER BY created_at DESC LIMIT 200')


@router.post('/admin/invite')
def invite(body: EmailInput, request: Request):
    actor = sec.role(request, 'admin')
    address = sec.email(body.email)
    sec.rate_limit(request.app.state.db, 'invite', actor['id'], 30)
    with request.app.state.db.connect() as c:
        c.lock()
        user = c.one('SELECT * FROM app_users WHERE email=%s', (address,))
        if user and user['verified']:
            raise HTTPException(409, 'This account already exists.')
        if not user:
            user = {'id': uid(), 'email': address}
            c.execute('INSERT INTO app_users(id,email,password,role,created_at) VALUES(%s,%s,%s,%s,%s)',
                      (user['id'], address, 'invitation-only', 'member', now()))
        audit(c, actor['id'], 'account.invite', user['id'])
        return {'message': 'Invitation prepared.', **send_token(request, c, user, 'invite')}


@router.patch('/admin/users/{user_id}')
def change_role(user_id: str, body: RoleInput, request: Request):
    actor = sec.role(request, 'admin')
    if body.role not in {'admin', 'member', 'viewer'}:
        raise HTTPException(422, 'Choose admin, member, or viewer.')
    with request.app.state.db.connect() as c:
        c.lock()
        # Authorization and mutation share the same transaction for concurrent demotions.
        current = c.one('SELECT * FROM app_users WHERE id=%s', (actor['id'],))
        if not current['active'] or current['role'] != 'admin':
            raise HTTPException(403, 'Administrator access is required.')
        target = c.one('SELECT * FROM app_users WHERE id=%s', (user_id,))
        if not target:
            raise HTTPException(404, 'Account not found.')
        admins = c.one("SELECT COUNT(*) AS n FROM app_users WHERE role='admin' AND active=1 AND verified=1")['n']
        if target['role'] == 'admin' and target['active'] and target['verified'] and admins <= 1 and (body.role != 'admin' or not body.active):
            raise HTTPException(409, 'Keep at least one active, verified administrator.')
        c.execute('UPDATE app_users SET role=%s,active=%s WHERE id=%s', (body.role, int(body.active), user_id))
        c.execute('DELETE FROM app_sessions WHERE user_id=%s', (user_id,))
        audit(c, actor['id'], 'account.access_changed', user_id)
    return {'ok': True}
