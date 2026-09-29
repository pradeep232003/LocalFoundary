"""Run on a different host once per minute. Alert webhook is configured by the operator."""
import argparse
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def https(value):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Monitor endpoints must be HTTPS URLs without embedded credentials.')
    return value


def transition(state, healthy, threshold=3):
    failures = 0 if healthy else state.get('failures', 0) + 1
    alarm = failures >= threshold
    if healthy:
        event = 'recovered' if state.get('alerted', False) else None
    else:
        event = 'down' if alarm and not state.get('alerted', False) else None
    return {'failures': failures, 'alerted': state.get('alerted', False), 'checked_at': time.time()}, event


def check(settings, state):
    opener = build_opener(NoRedirect, ProxyHandler({}))
    try:
        with opener.open(https(settings['health_url']), timeout=8) as response:
            body = json.loads(response.read(16000))
            healthy = response.status == 200 and body.get('status') == 'ok' and body.get('database') == 'connected'
    except Exception:
        healthy = False
    updated, event = transition(state, healthy)
    if event:
        payload = json.dumps({'event': 'local_foundry_' + event, 'application': str(settings.get('name', 'App'))[:80],
                              'checked_at': updated['checked_at']}).encode()
        request = Request(https(settings['alert_webhook']), data=payload, headers={'Content-Type':'application/json'}, method='POST')
        with opener.open(request, timeout=8) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError('Alert delivery failed; it will retry next run.')
        updated['alerted'] = event == 'down'
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    path = Path(args.config).resolve()
    if path.stat().st_mode & 0o077:
        raise ValueError('Keep the monitor configuration private (chmod 600).')
    state_path = path.with_suffix('.state.json')
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    result = check(json.loads(path.read_text()), state)
    temporary = state_path.with_suffix('.partial')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600)
        json.dump(result, stream)
    temporary.replace(state_path)
    print('External check:', 'alert active' if result['alerted'] else 'healthy' if result['failures'] == 0 else 'retry pending')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('External monitor or alert delivery failed. Configuration values were withheld.') from None
