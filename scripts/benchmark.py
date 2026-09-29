"""Capability benchmark: run graded build prompts and record what actually happened.

Every other check in this repository asks whether the builder still works. This one
asks how much it can build. It runs a fixed prompt set against a running builder and
a configured model, then records, per case, whether the build completed, whether
validation passed, whether the browser checks passed, how many automatic repairs it
needed, and what it cost. The point is the trend across runs, not any single result.

This spends real money on remote providers and creates real projects. Nothing runs
without --confirm. Projects are kept so the apps can be reviewed by hand, which is
the only way to judge whether a passing build is actually any good.

    .venv/bin/python scripts/benchmark.py --provider local --confirm
    .venv/bin/python scripts/benchmark.py --provider anthropic --tier 1 --budget 2 --confirm
    .venv/bin/python scripts/benchmark.py --report benchmark-results/latest.json
"""
import argparse
import datetime
import json
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app import config  # noqa: E402  (needs the path above)

PROMPTS = Path(__file__).resolve().parent / 'benchmark' / 'prompts.json'
# A build that has not finished in 25 minutes is not going to produce a useful
# result, and leaving it running spends budget with nobody watching.
CASE_TIMEOUT = 1500


def load_cases(path, tiers, only):
    data = json.loads(Path(path).read_text())
    cases = data['cases']
    if tiers:
        cases = [case for case in cases if case['tier'] in tiers]
    if only:
        wanted = set(only)
        unknown = wanted - {case['id'] for case in data['cases']}
        if unknown:
            raise SystemExit('Unknown case id(s): ' + ', '.join(sorted(unknown)))
        cases = [case for case in cases if case['id'] in wanted]
    if not cases:
        raise SystemExit('No cases selected.')
    return cases


def summarize_events(events):
    """Count repairs and collect the checks and errors a reviewer would want."""
    repairs, checks, errors, tools = 0, [], [], 0
    for event in events:
        kind = event.get('kind')
        if kind == 'repair':
            repairs += 1
        elif kind == 'tool':
            tools += 1
        elif kind == 'check':
            checks.append({'text': event.get('text', '')[:300], 'status': event.get('status')})
        elif kind in {'error', 'tool_error'}:
            errors.append(event.get('text', '')[:300])
    return {'repairs': repairs, 'tool_calls': tools, 'checks': checks, 'errors': errors[:8]}


class Builder:
    def __init__(self, client):
        self.client = client

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        if not response.is_success:
            raise RuntimeError(f'HTTP {response.status_code} from {path}: {response.text[:300]}')
        return response.json()

    def all_events(self, run_id):
        """Page through the run's events; the endpoint returns 100 at a time."""
        events, after = [], 0
        while True:
            page = self.request('GET', f'/runs/{run_id}', params={'after': after})
            events.extend(page['events'])
            if not page.get('more') or not page['events']:
                return page, events
            after = page['events'][-1]['id']


def run_case(builder, case, args):
    started = time.monotonic()
    record = {'id': case['id'], 'tier': case['tier'], 'title': case['title'],
              'profile': case['profile'], 'expect': case['expect'],
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        project = builder.request('POST', '/projects', json={
            'name': f"Benchmark {case['id']} {time.strftime('%Y%m%d-%H%M%S')}",
            'profile': case['profile']})
        record['project_id'] = project['id']
        launch = builder.request('POST', f"/projects/{project['id']}/build", json={
            'provider': args.provider,
            'budget_usd': 0 if args.provider == 'local' else args.budget,
            'max_input_tokens': args.max_input_tokens,
            'max_output_tokens': args.max_output_tokens,
            'max_repairs': args.max_repairs,
            'browser_checks': True,
            'share_screenshots': False,
            'prompt': case['prompt']})
        record['run_id'] = launch['run_id']
        print(f"  project {project['id']}  run {launch['run_id']}", flush=True)
    except RuntimeError as exc:
        record.update(outcome='harness_error', detail=str(exc))
        return record

    deadline = time.monotonic() + args.timeout
    status = None
    while time.monotonic() < deadline:
        try:
            status, events = builder.all_events(record['run_id'])
        except RuntimeError as exc:
            record.update(outcome='harness_error', detail=str(exc))
            return record
        if status['status'] != 'running':
            break
        time.sleep(3)
    else:
        try:
            builder.request('POST', f"/runs/{record['run_id']}/cancel", json={})
        except RuntimeError:
            pass
        status, events = builder.all_events(record['run_id'])
        record.update(outcome='timeout', detail=f'No result within {args.timeout}s; cancellation requested.')

    record['run_status'] = status['status']
    record['usage'] = status.get('usage') or {}
    record.update(summarize_events(events))
    record['seconds'] = round(time.monotonic() - started, 1)

    # The build finishing is not the same as the app being correct. Validation and
    # browser evidence are read from the project, not inferred from the run.
    try:
        project = builder.request('GET', f"/projects/{record['project_id']}")
        validation = project.get('last_validation') or {}
        record['validation_status'] = validation.get('status')
        record['validation_checks'] = [
            {'name': check.get('name'), 'status': check.get('status')}
            for check in validation.get('checks', [])]
        record['browser_checks'] = validation.get('browser_checks')
        visual = project.get('visual_checks') or []
        record['visual'] = [{'viewport': item.get('viewport'), 'status': item.get('status')} for item in visual[:6]]
    except RuntimeError as exc:
        record['validation_status'] = 'unknown'
        record.setdefault('detail', str(exc))

    if record.get('outcome') != 'timeout':
        if status['status'] != 'completed':
            record['outcome'] = 'build_failed'
        elif record.get('validation_status') != 'passed':
            record['outcome'] = 'validation_failed'
        elif not record.get('browser_checks') or not record.get('visual') or any(item['status'] != 'passed' for item in record['visual']):
            record['outcome'] = 'browser_failed'
        else:
            record['outcome'] = 'passed'
    return record


def write_report(results, meta, output):
    output.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    payload = {**meta, 'results': results}
    (output / f'benchmark-{stamp}.json').write_text(json.dumps(payload, indent=2))
    (output / 'latest.json').write_text(json.dumps(payload, indent=2))
    (output / 'latest.md').write_text(render_markdown(payload))
    return output / f'benchmark-{stamp}.json'


def render_markdown(payload):
    order = ['passed', 'browser_failed', 'validation_failed', 'build_failed', 'timeout', 'harness_error']
    counts = {name: sum(1 for item in payload['results'] if item['outcome'] == name) for name in order}
    total_cost = sum((item.get('usage') or {}).get('estimated_usd', 0) or 0 for item in payload['results'])
    lines = [
        f"# Capability benchmark · {payload['provider']} · {payload['model'] or 'unknown model'}",
        '',
        f"Run {payload['created_at']} · prompt set v{payload['prompt_version']} · "
        f"{len(payload['results'])} cases · about ${total_cost:.2f}",
        '',
        '| Case | Tier | Outcome | Validation | Repairs | Tokens in/out | Cost | Seconds |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |',
    ]
    for item in payload['results']:
        usage = item.get('usage') or {}
        tokens = f"{usage.get('input_tokens', 0):,}/{usage.get('output_tokens', 0):,}"
        cost = usage.get('estimated_usd')
        lines.append(
            f"| {item['title']} | {item['tier']} | **{item['outcome']}** | "
            f"{item.get('validation_status') or '—'} | {item.get('repairs', 0)} | {tokens} | "
            f"{('$%.3f' % cost) if cost else '—'} | {item.get('seconds', '—')} |")
    lines += ['', '## Pass rate by tier', '']
    for tier in sorted({item['tier'] for item in payload['results']}):
        rows = [item for item in payload['results'] if item['tier'] == tier]
        passed = sum(1 for item in rows if item['outcome'] == 'passed')
        lines.append(f"- Tier {tier}: {passed}/{len(rows)} passed")
    lines += ['', '## Review by hand', '',
              'A passing row means the build completed and the automated checks passed. '
              'It does not mean the app is good. Open each project and check these:', '']
    for item in payload['results']:
        lines.append(f"**{item['title']}** — {item.get('project_id', 'no project')} ({item['outcome']})")
        for expectation in item['expect']:
            lines.append(f"  - [ ] {expectation}")
        if item.get('errors'):
            lines.append(f"  - errors seen: {item['errors'][0][:200]}")
        lines.append('')
    lines += ['## Outcome counts', '']
    lines += [f'- {name}: {counts[name]}' for name in order if counts[name]]
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--provider', choices=['local', 'anthropic', 'openai'])
    parser.add_argument('--tier', type=int, action='append', dest='tiers',
                        help='Run only this tier; repeatable. Default: every tier.')
    parser.add_argument('--case', action='append', dest='cases', help='Run only this case id; repeatable.')
    parser.add_argument('--budget', type=float, default=2.0, help='USD budget per case for remote providers.')
    parser.add_argument('--max-repairs', type=int, default=2)
    parser.add_argument('--max-input-tokens', type=int, default=120000)
    parser.add_argument('--max-output-tokens', type=int, default=16000)
    parser.add_argument('--timeout', type=int, default=CASE_TIMEOUT)
    parser.add_argument('--prompts', default=str(PROMPTS))
    parser.add_argument('--output', default=str(ROOT / 'benchmark-results'))
    parser.add_argument('--report', help='Re-render markdown from an existing JSON result file and exit.')
    parser.add_argument('--list', action='store_true', help='List the prompt set and exit.')
    parser.add_argument('--confirm', action='store_true',
                        help='Authorize live model calls, new projects and sandbox execution.')
    args = parser.parse_args()

    if args.report:
        payload = json.loads(Path(args.report).read_text())
        print(render_markdown(payload))
        return

    cases = load_cases(args.prompts, set(args.tiers or []), args.cases)
    if args.list:
        for case in cases:
            print(f"tier {case['tier']}  {case['id']:<20} {case['profile']:<9} {case['title']}")
        return
    if not args.provider:
        raise SystemExit('--provider is required to run the benchmark.')
    if not args.confirm:
        raise SystemExit(
            f'No calls made. This would run {len(cases)} build(s) against the {args.provider} provider, '
            f'create {len(cases)} project(s), and execute sandbox commands. Remote providers may charge '
            f'your account (budget ${args.budget:.2f} per case). Add --confirm to authorize it.')

    headers = {'Authorization': 'Bearer ' + config.TOKEN}
    base = f'http://127.0.0.1:{config.PORT}/api'
    with httpx.Client(base_url=base, headers=headers, timeout=60, trust_env=False) as client:
        builder = Builder(client)
        try:
            settings = builder.request('GET', '/config')
        except (RuntimeError, httpx.HTTPError) as exc:
            raise SystemExit(f'Could not reach the builder at {base}. Start it first. ({exc})') from None
        provider_settings = settings['providers'].get(args.provider, {})
        if not provider_settings.get('configured'):
            raise SystemExit(f'The {args.provider} provider is not configured. No project was created.')
        model = provider_settings.get('model')
        print(f'Benchmarking {args.provider} · {model} · {len(cases)} case(s)\n', flush=True)

        results = []
        for index, case in enumerate(cases, 1):
            print(f"[{index}/{len(cases)}] tier {case['tier']} · {case['title']}", flush=True)
            record = run_case(builder, case, args)
            results.append(record)
            usage = record.get('usage') or {}
            print(f"  → {record['outcome']} · validation {record.get('validation_status')} · "
                  f"{record.get('repairs', 0)} repair(s) · "
                  f"${usage.get('estimated_usd', 0) or 0:.3f} · {record.get('seconds')}s\n", flush=True)

    meta = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'provider': args.provider, 'model': model,
            'prompt_version': json.loads(Path(args.prompts).read_text())['version'],
            'budget_usd_per_case': args.budget, 'max_repairs': args.max_repairs,
            'host': {'platform': sys.platform, 'python': sys.version.split()[0]}}
    path = write_report(results, meta, Path(args.output))
    passed = sum(1 for item in results if item['outcome'] == 'passed')
    print(f'{passed}/{len(results)} passed. Report: {path}')
    print(f"Markdown summary: {Path(args.output) / 'latest.md'}")
    print('Open each project and work through the review checklist before trusting a pass.')
    # Non-zero only when the harness itself could not do its job. A low pass rate is
    # a measurement, not a build failure, and should not break a scheduled run.
    if any(item['outcome'] == 'harness_error' for item in results):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
