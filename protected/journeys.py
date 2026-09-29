"""Authenticated UI contracts in a disposable, disconnected stack. No production credentials."""
import base64
import json
import sys
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ORIGIN = 'http://web:5173'


def run(options):
    evidence, results = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, chromium_sandbox=False)
        for viewport in ('desktop', 'mobile'):
            context = browser.new_context(viewport={'width': 390, 'height': 844} if viewport == 'mobile' else {'width': 1280, 'height': 800},
                                          accept_downloads=False, service_workers='block')
            context.route('**/*', lambda r: r.continue_() if urlsplit(r.request.url).netloc == 'web:5173' and urlsplit(r.request.url).scheme == 'http' else r.abort())
            context.route_web_socket('**/*', lambda r: r.connect_to_server() if urlsplit(r.url).netloc == 'web:5173' else r.close())
            page = context.new_page()
            page.set_default_timeout(7000)
            page.on('dialog', lambda d: d.dismiss())
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)[:500]))

            def capture(label):
                assert not errors, 'JavaScript error during journey'
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth + 2'), 'Horizontal overflow'
                evidence.append({'title': label, 'viewport': viewport, 'path': '/', 'status': 'passed',
                    'screenshot': base64.b64encode(page.screenshot(type='jpeg', quality=60)).decode()})
                results.append({'name': viewport + ': ' + label, 'status': 'passed'})

            def login(role):
                page.goto(ORIGIN, wait_until='domcontentloaded')
                page.get_by_label('Email address', exact=True).fill(role+'@journey.test')
                page.get_by_label('Password', exact=True).fill(options['password'])
                page.get_by_role('button', name='Sign in →', exact=True).click()
                expect(page.get_by_role('heading', name='My workspace', exact=True)).to_be_visible()

            try:
                page.goto(ORIGIN)
                expect(page.get_by_role('button', name='Create an account', exact=True)).to_be_visible()
                capture('Sign in')
                page.get_by_role('button', name='Create an account', exact=True).click()
                page.get_by_label('Email address', exact=True).fill(viewport+'@journey.test')
                page.get_by_label('Password', exact=True).fill(options['password'])
                page.get_by_role('button', name='Create account →', exact=True).click()
                page.get_by_role('button', name='Open account link', exact=True).click()
                page.get_by_role('button', name='Complete account request', exact=True).click()
                expect(page.get_by_role('button', name='Sign in →', exact=True)).to_be_visible()
                capture('Registration and email verification in preview')
                login('member')
                page.get_by_label('New note', exact=True).fill('Journey record '+viewport)
                page.get_by_role('button', name='+ Add note', exact=True).click()
                expect(page.get_by_text('Journey record '+viewport, exact=True)).to_be_visible()
                page.reload()
                expect(page.get_by_text('Journey record '+viewport, exact=True)).to_be_visible()
                capture('Member record persists after reload')
                page.locator('article').filter(has=page.get_by_text('Journey record '+viewport, exact=True)).get_by_label('Delete note').click()
                expect(page.get_by_text('Journey record '+viewport, exact=True)).to_have_count(0)
                page.get_by_role('button', name='Billing', exact=True).click()
                expect(page.get_by_role('heading', name='Billing', exact=True)).to_be_visible()
                capture('Billing with integrations disabled')
                page.get_by_label('Sign out', exact=True).click()
                expect(page.get_by_role('button', name='Sign in →', exact=True)).to_be_visible()
                login('viewer')
                expect(page.get_by_label('New note', exact=True)).to_have_count(0)
                capture('Viewer cannot edit records')
                page.get_by_label('Sign out', exact=True).click()
                login('admin')
                page.get_by_role('button', name='People & access', exact=True).click()
                expect(page.get_by_label('Role for member@journey.test')).to_be_visible()
                capture('Administrator people and roles')
                page.get_by_role('button', name='Operations', exact=True).click()
                expect(page.get_by_role('heading', name='Connected services')).to_be_visible()
                capture('Administrator operations')
                page.get_by_label('Sign out', exact=True).click()
                page.reload()
                expect(page.get_by_role('button', name='Sign in →', exact=True)).to_be_visible()
                capture('Logout remains signed out after reload')
            except Exception as exc:
                # Playwright errors can include input values: never return traces/HTML/credentials.
                results.append({'name': viewport + ': current journey', 'status': 'failed', 'detail': type(exc).__name__ + '; check the last successful step and the protected journey selectors.'})
            finally:
                context.close()
        browser.close()
    return {'status': 'passed' if all(r['status'] == 'passed' for r in results) else 'failed', 'checks': results, 'evidence': evidence,
            'provider_checkout': 'blocked: disconnected preview; requires separate Stripe test-mode acceptance'}


if __name__ == '__main__':
    print(json.dumps(run(json.loads(sys.stdin.read(4000)))))
