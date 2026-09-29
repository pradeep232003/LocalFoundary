"""Interactive acceptance against your HTTPS staging app and real provider test accounts.
This sends a verification email and creates a Stripe TEST checkout. No live mode allowed.
"""
import argparse
import datetime
import getpass
import json
from pathlib import Path
import secrets
import time
from urllib.parse import parse_qs, urlsplit
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--product', required=True)
    parser.add_argument('--output', default='provider-acceptance.json')
    args = parser.parse_args()
    u = urlsplit(args.origin)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
        raise SystemExit('Use your staging HTTPS origin only.')
    origin = args.origin.rstrip('/')
    checks = []
    try:
        with httpx.Client(base_url=origin, headers={'Origin':origin}, timeout=30, trust_env=False, follow_redirects=False) as client:
            def call(method, path, **kw):
                response = client.request(method, path, **kw)
                if response.status_code >= 300:
                    raise RuntimeError('Staging request failed with HTTP '+str(response.status_code))
                return response.json()
            settings = call('GET', '/api/config')
            if settings.get('payments') != 'test' or settings.get('environment') != 'production' or not settings.get('signup'):
                raise RuntimeError('Use an HTTPS staging deployment with PAYMENT_MODE=test, APP_ENV=production and test signup enabled.')
            email = input('Disposable email address you control: ').strip()
            password = getpass.getpass('New test account password (12+ characters): ')
            registration = call('POST', '/api/auth/register', json={'email':email, 'password':password})
            if 'preview_link' in registration:
                raise RuntimeError('Production registration exposed a preview token.')
            print('Read the actual verification email. Paste its complete link privately below.')
            link = getpass.getpass('Verification link: ')
            parsed = urlsplit(link)
            token = parse_qs(parsed.fragment).get('token', [''])[0]
            if parsed.scheme+'://'+parsed.netloc != origin or not token:
                raise RuntimeError('Verification link must belong to this staging origin.')
            call('POST', '/api/auth/complete/verify', json={'token':token})
            checks.append({'name':'Real email delivery and verification', 'status':'passed', 'evidence':'Operator supplied a token from the received email; production API withheld the token.'})
            session = call('POST', '/api/auth/login', json={'email':email, 'password':password})
            client.headers['X-CSRF-Token'] = session['csrf']
            request = {'product':args.product, 'request_id':secrets.token_hex(16)}
            checkout = call('POST', '/api/billing/checkout', json=request)
            again = call('POST', '/api/billing/checkout', json=request)
            if again != checkout:
                raise RuntimeError('Checkout retry was not idempotent.')
            checkout_url = urlsplit(checkout['url'])
            if checkout_url.scheme != 'https' or checkout_url.hostname != 'checkout.stripe.com':
                raise RuntimeError('Unexpected checkout host.')
            print('Open this Stripe test checkout in your browser and use Stripe test payment details:')
            print(checkout['url'])  # One test-session link; deliberately excluded from the saved report.
            input('Press Enter after completing the test checkout: ')
            deadline = time.monotonic()+90
            while time.monotonic() < deadline:
                orders = call('GET', '/api/billing/orders')
                if any(row['id'] == checkout['order_id'] and row['status'] == 'paid' for row in orders):
                    break
                time.sleep(2)
            else:
                raise RuntimeError('No paid order arrived through the real provider webhook within 90 seconds.')
            checks.append({'name':'Real Stripe test checkout, idempotency and paid webhook', 'status':'passed', 'order_id':checkout['order_id']})
            call('POST', '/api/auth/logout', json={})
            if client.get('/api/notes').status_code != 401:
                raise RuntimeError('Logout left protected access available.')
            checks.append({'name':'HTTPS session logout', 'status':'passed'})
            checks.append({'name':'Outgoing webhook receipt and signature', 'status':'blocked', 'detail':'Verify the order.paid event and signature at your configured receiver. See PROVIDER-ACCEPTANCE.md.'})
    except (Exception, KeyboardInterrupt) as exc:
        checks.append({'name':'Provider acceptance', 'status':'failed', 'detail':str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__})
    report = {'version':'0.11.0','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'checks':checks,
              'status':'failed' if any(c['status']=='failed' for c in checks) else 'incomplete' if any(c['status']=='blocked' for c in checks) else 'passed'}
    Path(args.output).write_text(json.dumps(report, indent=2))
    print('Saved provider acceptance:', report['status'])
    return 1 if report['status']=='failed' else 2 if report['status']=='incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
