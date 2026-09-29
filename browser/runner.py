"""Trusted runner: fixed actions only, ephemeral context, same-origin requests."""
import base64
import json
import sys
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ORIGIN = 'http://web:5173'


def same_origin(url):
    parsed = urlsplit(url)
    return parsed.scheme == 'http' and parsed.netloc == 'web:5173'


def inspect(options):
    errors, failed_requests = [], []
    def remember(target, value):
        if len(target) < 15:
            target.append(str(value)[:1000])
    with sync_playwright() as playwright:
        # Docker is the outer isolation boundary. No SYS_ADMIN, host IPC, host
        # networking, host files, cookies, or credentials are made available.
        browser = playwright.chromium.launch(headless=True, chromium_sandbox=False)
        viewport = {'width': 390, 'height': 844} if options['viewport'] == 'mobile' else {'width': 1280, 'height': 800}
        context = browser.new_context(viewport=viewport, accept_downloads=False, service_workers='block')
        context.route('**/*', lambda route: route.continue_() if same_origin(route.request.url) else route.abort())
        context.route_web_socket('**/*', lambda route: route.connect_to_server()
                                 if urlsplit(route.url).scheme == 'ws' and urlsplit(route.url).netloc == 'web:5173'
                                 else route.close())
        page = context.new_page()
        context.on('page', lambda popup: popup.close() if popup != page else None)
        page.on('dialog', lambda dialog: dialog.dismiss())
        page.on('pageerror', lambda exc: remember(errors, exc))
        page.on('console', lambda message: remember(errors, message.text) if message.type == 'error' else None)
        page.on('requestfailed', lambda request: remember(failed_requests, request.url + ': ' + str(request.failure)))
        page.set_default_timeout(5000)
        response_status = None
        action_results = []
        try:
            response = page.goto(ORIGIN + options['path'], wait_until='domcontentloaded', timeout=20000)
            response_status = response.status if response else None
            # A short, bounded render window; no arbitrary model-authored sleeps/eval.
            page.wait_for_timeout(750)
            for action in options['actions']:
                locator = page.locator(action['selector']).first
                if action['action'] == 'click':
                    locator.click()
                elif action['action'] == 'fill':
                    locator.fill(action['value'])
                else:
                    locator.wait_for(state='visible')
                action_results.append({'action': action['action'], 'selector': action['selector'], 'status': 'passed'})
            page.wait_for_timeout(250)
        except Exception as exc:
            remember(errors, exc)
        if not same_origin(page.url):
            raise ValueError('Preview attempted to leave its allowed origin.')
        text = page.locator('body').evaluate('node => node.innerText.slice(0, 12000)', timeout=5000)
        overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth + 2')
        screenshot = page.screenshot(type='jpeg', quality=65, full_page=False, timeout=10000)
        report = {'title': page.evaluate('document.title.slice(0, 300)'), 'text': text, 'url': page.url,
                  'status_code': response_status, 'errors': errors, 'failed_requests': failed_requests,
                  'horizontal_overflow': overflow, 'actions': action_results,
                  'screenshot': base64.b64encode(screenshot).decode()}
        browser.close()
        return report


if __name__ == '__main__':
    request = json.loads(sys.stdin.read(32000))
    print(json.dumps(inspect(request)))
