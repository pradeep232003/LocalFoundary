import hmac
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from . import security as sec
from .db import audit, now

router = APIRouter()


def authorize(request):
    expected = request.app.state.settings.ops_token
    if not expected or not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + expected):
        raise HTTPException(401, 'Internal monitoring authentication is required.')


@router.get('/api/admin/ops')
def dashboard(request: Request):
    sec.role(request, 'admin')
    settings = request.app.state.settings
    with request.app.state.db.connect() as c:
        return {'environment': settings.env, 'payment_mode': settings.payment_mode,
            'integrations': {'enabled': settings.online, 'email': bool(settings.resend_key and settings.email_from), 'webhook': bool(settings.webhook_url)},
            'metrics': c.all('SELECT * FROM app_metrics ORDER BY route,method,status'),
            'audit': c.all('SELECT * FROM app_audit ORDER BY created_at DESC LIMIT 100'),
            'deliveries': c.all('SELECT id,kind,status,attempts,last_error,created_at FROM app_outbox ORDER BY created_at DESC LIMIT 100'),
            'alerts': c.all('SELECT * FROM app_alerts ORDER BY created_at DESC LIMIT 30'),
            'worker': c.one('SELECT heartbeat FROM app_worker WHERE id=%s', ('delivery',))}


@router.post('/api/admin/deliveries/{identifier}/retry')
def retry(identifier: str, request: Request):
    actor = sec.role(request, 'admin')
    with request.app.state.db.connect() as c:
        # Stay inside provider idempotency retention; old emails require a fresh reset/invite.
        row = c.one('SELECT * FROM app_outbox WHERE id=%s', (identifier,))
        if not row or row['status'] != 'dead' or row['created_at'] < now()-23*3600:
            raise HTTPException(409, 'Only recent failed deliveries can be retried. Request a new account email for an expired delivery.')
        c.execute("UPDATE app_outbox SET status='queued',attempts=0,available_at=%s,lease_until=0 WHERE id=%s", (now(), identifier))
        audit(c, actor['id'], 'delivery.retry', identifier)
    return {'ok': True}


@router.get('/ops/metrics', response_class=PlainTextResponse)
def metrics(request: Request):
    authorize(request)
    with request.app.state.db.connect() as c:
        rows = c.all('SELECT * FROM app_metrics')
        queue = c.all('SELECT status,COUNT(*) AS n FROM app_outbox GROUP BY status')
        heartbeat = c.one('SELECT heartbeat FROM app_worker WHERE id=%s', ('delivery',))
    lines = ['# TYPE foundry_http_requests_total counter', '# TYPE foundry_http_duration_seconds_sum counter']
    for row in rows:
        # Route names are registered templates, never arbitrary user-supplied URLs.
        labels = '{route="%s",method="%s",status="%s"}' % (row['route'].replace('"', ''), row['method'], row['status'])
        lines.extend(['foundry_http_requests_total'+labels+' '+str(row['count']),
                      'foundry_http_duration_seconds_sum'+labels+' '+str(row['duration_ms']/1000)])
    lines.append('# TYPE foundry_delivery_queue gauge')
    lines.extend('foundry_delivery_queue{status="%s"} %s' % (row['status'], row['n']) for row in queue)
    lines.extend(['# TYPE foundry_worker_heartbeat_seconds gauge', 'foundry_worker_heartbeat_seconds '+str(heartbeat['heartbeat'] if heartbeat else 0)])
    return '\n'.join(lines)+'\n'


@router.post('/ops/alerts')
async def alerts(request: Request):
    authorize(request)
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get('alerts'), list) or len(body['alerts']) > 50:
        raise HTTPException(422, 'Invalid alert batch.')
    with request.app.state.db.connect() as c:
        for item in body['alerts']:
            if not isinstance(item, dict):
                raise HTTPException(422, 'Invalid alert.')
            identifier = str(item.get('fingerprint', ''))[:128]
            name = str(item.get('labels', {}).get('alertname', 'Alert'))[:120]
            status = 'resolved' if item.get('status') == 'resolved' else 'firing'
            c.execute('INSERT INTO app_alerts(id,name,status,created_at) VALUES(%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET status=excluded.status,created_at=excluded.created_at', (identifier, name, status, now()))
    return {'ok': True}
