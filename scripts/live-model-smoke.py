"""Opt-in full build against your running builder. Keeps the resulting app for review."""
import argparse
from pathlib import Path
import sys
import time

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import config

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--provider', choices=['local', 'anthropic', 'openai'], required=True)
parser.add_argument('--budget', type=float, default=1.0, help='Estimated USD budget (remote providers can incur charges)')
parser.add_argument('--profile', choices=['starter', 'accounts'], default='accounts')
parser.add_argument('--confirm', action='store_true', help='Authorize model calls, a new project, and sandbox execution')
args = parser.parse_args()
if not args.confirm:
    raise SystemExit('No calls made. Add --confirm to authorize a new acceptance project and live model calls. Remote providers may charge your account.')
headers = {'Authorization': 'Bearer ' + config.TOKEN}
with httpx.Client(base_url=f'http://127.0.0.1:{config.PORT}/api', headers=headers, timeout=45, trust_env=False) as client:
    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        if not response.is_success:
            raise SystemExit(f'Builder returned HTTP {response.status_code}; inspect the local UI for details.')
        return response.json()
    settings = request('GET', '/config')
    if not settings['providers'][args.provider]['configured']:
        raise SystemExit('Selected provider is not configured. No project was created.')
    project = request('POST', '/projects', json={'name': 'Live model acceptance ' + time.strftime('%Y%m%d-%H%M%S'), 'profile': args.profile})
    result = request('POST', f'/projects/{project["id"]}/build', json={
        'provider': args.provider, 'budget_usd': 0 if args.provider == 'local' else args.budget,
        'max_input_tokens': 80000, 'max_output_tokens': 12000, 'max_repairs': 1,
        'browser_checks': True, 'share_screenshots': False,
        'prompt': 'Add a search filter for the existing notes and an accessible clear-filter button. Preserve every account, billing, role and operations screen and all existing accessible names used by protected user journeys. Keep the PostgreSQL-backed notes API, authentication, ownership and health endpoint. Keep it responsive. Add a backend regression test. Do not request dependencies or publish anything.'})
    print('Created acceptance project:', project['id'])
    print('Live model run:', result['run_id'])
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        status = request('GET', f'/runs/{result["run_id"]}')
        if status['status'] != 'running':
            print('Result:', status['status'])
            if status['status'] != 'completed':
                raise SystemExit('Live acceptance did not complete. Inspect Activity and Versions; all completed edits remain available.')
            project = request('GET', f'/projects/{project["id"]}')
            if project['last_validation']['status'] != 'passed':
                raise SystemExit('Current source is not validated.')
            print('Checks passed. Review the actual app and screenshots in Local Foundry before trusting the result.')
            break
        time.sleep(2)
    else:
        request('POST', f'/runs/{result["run_id"]}/cancel', json={})
        raise SystemExit('Acceptance timed out; requested cancellation. Review the saved project.')
