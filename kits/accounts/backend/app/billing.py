import hashlib
import hmac
import json
import re
from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from . import integrations, security as sec
from .db import audit, now, uid

router = APIRouter(prefix='/api/billing')


class Checkout(BaseModel):
    product: str = Field(max_length=40)
    request_id: str = Field(pattern=r'^[a-f0-9-]{32,36}$')


@router.get('/products')
def products(request: Request):
    sec.current_user(request)
    settings = request.app.state.settings
    return {'mode': settings.payment_mode, 'products': [
        {'id': key, 'name': item['name'], 'amount': item['amount'], 'currency': item['currency']}
        for key, item in settings.catalog.items()]}


@router.get('/orders')
def orders(request: Request):
    user = sec.current_user(request)
    with request.app.state.db.connect() as c:
        return c.all('SELECT id,product,amount,currency,status,refunded,created_at FROM app_orders WHERE user_id=%s ORDER BY created_at DESC LIMIT 100', (user['id'],))


@router.post('/checkout')
def checkout(body: Checkout, request: Request):
    user = sec.role(request, 'admin', 'member')
    settings, database = request.app.state.settings, request.app.state.db
    if settings.payment_mode == 'off' or not settings.online:
        raise HTTPException(503, 'Payments are disabled. Preview never contacts Stripe.')
    item = settings.catalog.get(body.product)
    if not item:
        raise HTTPException(404, 'Product not found.')
    sec.rate_limit(database, 'checkout', user['id'], 20)
    with database.connect() as c:
        c.execute('''INSERT INTO app_orders(id,user_id,request_id,product,price_id,amount,currency,created_at)
                     VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,request_id) DO NOTHING''',
                  (uid(), user['id'], body.request_id, body.product, item['price_id'], item['amount'], item['currency'], now()))
        order = c.one('SELECT * FROM app_orders WHERE user_id=%s AND request_id=%s', (user['id'], body.request_id))
    if order['product'] != body.product or order['created_at'] < now()-23*3600:
        raise HTTPException(409, 'Start a new checkout with a new request ID.')
    if order['status'] != 'pending':
        raise HTTPException(409, 'This order is already closed.')
    if order['checkout_url']:
        return {'url': order['checkout_url'], 'order_id': order['id']}
    # All order and redirect values are selected server-side. Never accept a client price or URL.
    try:
        with integrations.client(settings) as http:
            headers = {'Authorization': 'Bearer ' + settings.stripe_key}
            price = http.get('https://api.stripe.com/v1/prices/' + order['price_id'], headers=headers)
            price.raise_for_status()
            price = price.json()
            if not price.get('active') or price.get('type') != 'one_time' or price.get('unit_amount') != order['amount'] or price.get('currency') != order['currency'] or bool(price.get('livemode')) != (settings.payment_mode == 'live'):
                raise HTTPException(409, 'The configured price does not match Stripe. Contact the administrator.')
            response = http.post('https://api.stripe.com/v1/checkout/sessions', headers={**headers, 'Idempotency-Key': 'checkout/' + order['id']}, data={
                'mode': 'payment', 'line_items[0][price]': order['price_id'], 'line_items[0][quantity]': '1',
                'client_reference_id': order['id'], 'metadata[order_id]': order['id'],
                'payment_intent_data[metadata][order_id]': order['id'],
                'success_url': settings.origin + '/?checkout=returned', 'cancel_url': settings.origin + '/?checkout=cancelled'})
            response.raise_for_status()
            session = response.json()
            parsed = urlsplit(session['url'])
            if parsed.scheme != 'https' or parsed.hostname != 'checkout.stripe.com' or parsed.username or parsed.port not in (None, 443) or not re.fullmatch(r'cs_[A-Za-z0-9_]+', session['id']):
                raise ValueError('Unexpected checkout response')
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Checkout is temporarily unavailable. Retry the same request.') from None
    with database.connect() as c:
        c.execute('UPDATE app_orders SET session_id=%s,checkout_url=%s WHERE id=%s', (session['id'], session['url'], order['id']))
        audit(c, user['id'], 'checkout.created', order['id'])
    return {'url': session['url'], 'order_id': order['id']}


def verify_signature(raw, signature, secret):
    try:
        parts = [part.split('=', 1) for part in signature.split(',')]
        stamps = [value for key, value in parts if key == 't']
        if len(stamps) != 1 or abs(now() - int(stamps[0])) > 300:
            return False
        expected = hmac.new(secret.encode(), stamps[0].encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(value, expected) for key, value in parts if key == 'v1')
    except (ValueError, TypeError):
        return False


@router.post('/webhook')
async def webhook(request: Request):
    settings = request.app.state.settings
    if settings.payment_mode == 'off' or not settings.online:
        raise HTTPException(503, 'Payments are disabled.')
    raw = await request.body()
    if not verify_signature(raw, request.headers.get('stripe-signature', ''), settings.stripe_webhook_secret):
        raise HTTPException(400, 'Invalid payment signature.')
    try:
        event = json.loads(raw)
        identifier, kind, obj = event['id'], event['type'], event['data']['object']
        if not isinstance(identifier, str) or len(identifier) > 200 or not isinstance(kind, str) or not isinstance(obj, dict) or event.get('livemode') is not (settings.payment_mode == 'live'):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, 'Invalid payment event.') from None
    with request.app.state.db.connect() as c:
        # Event insert and all effects commit atomically. Stripe retries any non-2xx response.
        inserted = c.one('INSERT INTO app_stripe_events(id,type,created_at) VALUES(%s,%s,%s) ON CONFLICT(id) DO NOTHING RETURNING id', (identifier, kind, now()))
        if not inserted:
            return {'received': True, 'duplicate': True}
        checkout_events = {'checkout.session.completed', 'checkout.session.async_payment_succeeded', 'checkout.session.async_payment_failed', 'checkout.session.expired'}
        if kind in checkout_events:
            lock = '' if c.sqlite else ' FOR UPDATE'
            order = c.one('SELECT * FROM app_orders WHERE id=%s' + lock, (obj.get('client_reference_id', ''),))
            if not order:
                raise HTTPException(400, 'Payment event did not match a known order.')
            # A webhook may race the checkout HTTP response. Retry until its session is persisted.
            if not order['session_id']:
                raise HTTPException(503, 'Checkout is still being prepared.')
            if (obj.get('id') != order['session_id'] or obj.get('mode') != 'payment'
                or obj.get('amount_total') != order['amount'] or obj.get('currency') != order['currency']):
                raise HTTPException(400, 'Payment event did not match the order.')
            paid = kind in {'checkout.session.completed', 'checkout.session.async_payment_succeeded'} and obj.get('payment_status') == 'paid'
            intent = obj.get('payment_intent')
            if paid and (not isinstance(intent, str) or not re.fullmatch(r'pi_[A-Za-z0-9]+', intent)):
                raise HTTPException(400, 'Missing payment reference.')
            if paid and order['status'] not in {'paid', 'refunded', 'partially_refunded'}:
                c.execute("UPDATE app_orders SET status='paid',payment_intent=%s WHERE id=%s", (intent, order['id']))
                audit(c, 'stripe', 'order.paid', order['id'])
                integrations.event(c, settings, 'order.paid', {'order_id': order['id'], 'user_id': order['user_id'], 'product': order['product']})
            elif kind in {'checkout.session.expired', 'checkout.session.async_payment_failed'} and order['status'] == 'pending':
                c.execute('UPDATE app_orders SET status=%s WHERE id=%s', ('expired' if kind.endswith('expired') else 'failed', order['id']))
        elif kind == 'charge.refunded':
            lock = '' if c.sqlite else ' FOR UPDATE'
            order = c.one('SELECT * FROM app_orders WHERE payment_intent=%s' + lock, (obj.get('payment_intent', ''),))
            if not order:
                # May arrive before the paid event. Do not acknowledge and lose the update.
                raise HTTPException(503, 'Payment reference is not ready.')
            amount = obj.get('amount_refunded')
            if type(amount) is not int or not 0 <= amount <= order['amount'] or obj.get('currency') != order['currency']:
                raise HTTPException(400, 'Invalid refund amount.')
            if amount > order['refunded']:
                c.execute('UPDATE app_orders SET refunded=%s,status=%s WHERE id=%s',
                          (amount, 'refunded' if amount == order['amount'] else 'partially_refunded', order['id']))
                audit(c, 'stripe', 'order.refunded', order['id'])
    return {'received': True}
