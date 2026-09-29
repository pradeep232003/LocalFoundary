import json
import logging
import secrets
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from . import auth, billing, ops, security as sec
from .db import Database, audit, now, uid

log = logging.getLogger('foundry.requests')


class RequestBoundary:
    """Bound bodies before FastAPI parses JSON. No request bodies/tokens in logs."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > 65536:
                return await JSONResponse({'detail': 'Request body is too large.'}, status_code=413)(scope, receive, send)
            chunks.append(message.get('body', b''))
            if not message.get('more_body'):
                break
        consumed = False
        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            return await receive()
        await self.app(scope, bounded_receive, send)


def create_app(settings, database=None):
    settings.validate()
    app = FastAPI(title='Accounts & billing', docs_url=None if settings.production else '/docs', redoc_url=None,
                  openapi_url=None if settings.production else '/openapi.json')
    app.state.settings = settings
    app.state.db = database or Database(settings.database_url)
    app.state.dummy_password = sec.hash_password(secrets.token_urlsafe(32))
    app.add_middleware(RequestBoundary)

    @app.middleware('http')
    async def observe(request, call_next):
        started, identifier = time.monotonic(), uid()
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse({'detail': 'An internal error occurred.', 'request_id': identifier}, status_code=500)
        response.headers.update({'X-Request-ID': identifier, 'X-Content-Type-Options': 'nosniff',
                                 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        duration = int((time.monotonic()-started)*1000)
        route = getattr(request.scope.get('route'), 'path', 'unmatched')
        method = request.method if request.method in {'GET','POST','PATCH','PUT','DELETE','HEAD','OPTIONS'} else 'OTHER'
        if route not in {'/ops/metrics', '/api/health'}:
            log.warning(json.dumps({'event': 'http_request', 'request_id': identifier, 'route': route,
                                    'method': method, 'status': response.status_code, 'duration_ms': duration}))
            try:
                # Run synchronous database work outside the event loop.
                from starlette.concurrency import run_in_threadpool
                def record():
                    with app.state.db.connect() as c:
                        c.execute('''INSERT INTO app_metrics(route,method,status,count,duration_ms) VALUES(%s,%s,%s,1,%s)
                            ON CONFLICT(route,method,status) DO UPDATE SET count=app_metrics.count+1,duration_ms=app_metrics.duration_ms+excluded.duration_ms''',
                                  (route, method, response.status_code, duration))
                await run_in_threadpool(record)
            except Exception:
                log.error(json.dumps({'event': 'metrics_write_failed', 'request_id': identifier}))
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail': 'Check the submitted fields.'}, status_code=422)

    @app.get('/api/health')
    def health():
        try:
            with app.state.db.connect() as c:
                c.one('SELECT id FROM app_users LIMIT 1')
            return {'status': 'ok', 'database': 'connected'}
        except Exception:
            raise HTTPException(503, 'Database is not ready.') from None

    @app.get('/api/config')
    def config():
        return {'environment': settings.env, 'signup': settings.signup, 'payments': settings.payment_mode,
                'roles': ['admin', 'member', 'viewer']}

    class RecordInput(BaseModel):
        text: str = Field(min_length=1, max_length=4000)

    @app.get('/api/notes')
    def notes(request: Request):
        user = sec.current_user(request)
        with app.state.db.connect() as c:
            return c.all('SELECT id,text,created_at FROM app_records WHERE user_id=%s ORDER BY created_at DESC LIMIT 100', (user['id'],))

    @app.post('/api/notes')
    def add_note(body: RecordInput, request: Request):
        user = sec.role(request, 'member', 'admin')
        sec.rate_limit(app.state.db, 'records', user['id'], 60, 60)
        identifier = uid()
        with app.state.db.connect() as c:
            c.execute('INSERT INTO app_records(id,user_id,text,created_at) VALUES(%s,%s,%s,%s)', (identifier, user['id'], body.text, now()))
            audit(c, user['id'], 'record.created', identifier)
        return {'id': identifier, 'text': body.text}

    @app.delete('/api/notes/{identifier}')
    def delete_note(identifier: str, request: Request):
        user = sec.role(request, 'member', 'admin')
        with app.state.db.connect() as c:
            result = c.execute('DELETE FROM app_records WHERE id=%s AND user_id=%s', (identifier, user['id']))
            if not result.rowcount:
                raise HTTPException(404, 'Record not found.')
            audit(c, user['id'], 'record.deleted', identifier)
        return {'ok': True}

    for router in (auth.router, billing.router, ops.router):
        app.include_router(router)
    return app
