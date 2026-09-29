"""Opt-in real Docker acceptance test. No paid model calls or GitHub writes."""
import io
import json
import os
import re
import threading
import zipfile

import httpx
import pytest

from app import config, db, files, main, recovery, releases, sandbox, validation, visual
from app.process import run

pytestmark = pytest.mark.skipif(os.environ.get('FOUNDRY_LIVE_DOCKER') != '1',
                                reason='Requires explicit FOUNDRY_LIVE_DOCKER=1 and cached Docker images')


def test_real_accounts_postgres_and_offline_preview(client, tmp_path):
    """Real PostgreSQL login, verification, ownership and roles; no provider calls."""
    identifier = client.post('/api/projects', json={'name':'Disposable accounts acceptance','profile':'accounts'}).json()['id']
    release_root, release_name = None, None
    try:
        url = sandbox.start(identifier)
        with httpx.Client(base_url=url, timeout=20, trust_env=False, headers={'Origin':url}) as browser:
            assert browser.get('/api/notes').status_code == 401
            signup = browser.post('/api/auth/register', json={'email':'acceptance@example.com','password':'disposable acceptance password'})
            signup.raise_for_status()
            token = signup.json()['preview_link'].split('token=')[1]
            browser.post('/api/auth/complete/verify', json={'token':token}).raise_for_status()
            signed_in = browser.post('/api/auth/login', json={'email':'acceptance@example.com','password':'disposable acceptance password'})
            signed_in.raise_for_status()
            browser.headers['X-CSRF-Token'] = signed_in.json()['csrf']
            browser.post('/api/notes', json={'text':'Private PostgreSQL note'}).raise_for_status()
            assert browser.get('/api/notes').json()[0]['text'] == 'Private PostgreSQL note'
            assert browser.get('/api/admin/users').status_code == 403
            assert browser.post('/api/notes', headers={'X-CSRF-Token':'wrong'}, json={'text':'blocked'}).status_code == 403
            assert browser.post('/api/billing/checkout', json={'product':'starter','request_id':'a'*32}).status_code == 503
            browser.post('/api/auth/logout', json={}).raise_for_status()
            assert browser.get('/api/notes').status_code == 401
        report = validation.run(identifier, 'accounts acceptance', threading.Event(), browser_checks=True)
        assert report['status'] == 'passed'
        assert len(visual.listing(identifier)) >= 18
        release_root = tmp_path/'accounts-release'
        with zipfile.ZipFile(io.BytesIO(releases.bundle(identifier, report, report['source_digest']))) as archive:
            archive.extractall(release_root)
        run(['bash', str(release_root/'build-release.sh')], timeout=300)
        env = release_root/'.env'
        env.write_text(env.read_text().replace('APP_PORT=8080', 'APP_PORT=0'))
        settings = dict(line.split('=', 1) for line in env.read_text().splitlines() if '=' in line)
        release_name = settings['RELEASE_NAME']
        assert re.fullmatch(r'foundry-release-[0-9a-f]{8}', release_name)
        stage_settings = {**settings, 'DATABASE_PASSWORD':__import__('secrets').token_hex(32), 'APP_PORT':'0'}
        (release_root/'.env.stage').write_text('\n'.join(k+'='+v for k,v in stage_settings.items())+'\n')
        (release_root/'.env.stage').chmod(0o600)
        ops = [__import__('sys').executable, str(release_root/'ops.py')]
        run([*ops, 'stage'], timeout=240)
        run([*ops, 'deploy', '--overlays', 'none'], timeout=500)
        state = json.loads((release_root/'.ops/state.json').read_text())
        assert state['phase'] == 'healthy'
        run([*ops, 'backup'], timeout=500)
        backups = list((release_root/'.ops/backups').glob('*.lfb'))
        assert len(backups) >= 2
        assert all(json.loads(p.with_suffix('.json').read_text())['restored'] for p in backups)
        # Re-deploy the same schema, then exercise compatible image rollback.
        run([*ops, 'deploy'], timeout=500)
        run([*ops, 'rollback'], timeout=240)
        assert json.loads((release_root/'.ops/state.json').read_text())['phase'] == 'healthy'
    finally:
        if release_root and release_name:
            for suffix, env_name in [('', '.env'), ('-stage', '.env.stage')]:
                run(['docker','compose','--env-file',str(release_root/env_name), '-f',str(release_root/'compose.yaml'),
                     '-p',release_name+suffix,'down','--volumes','--timeout','5'], timeout=60)
            tag = settings['RELEASE_TAG']
            run(['docker','image','rm',*[release_name+'-'+service+':'+tag for service in ('api','web','egress')]], timeout=30)
        # Only the uniquely-created disposable acceptance stack is removed.
        sandbox.command(identifier, 'down', '--volumes', '--timeout', '5', timeout=60)


def test_real_browser_recovery_and_production_release(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'OFFLINE_ONLY', True)
    project_id = client.post('/api/projects', json={'name': 'Disposable v0.4 acceptance'}).json()['id']
    created_ids = [project_id]
    compose = None
    release_name = None
    try:
        url = sandbox.start(project_id)
        with httpx.Client(base_url=url, timeout=20, trust_env=False) as browser:
            response = browser.post('/api/notes', json={'text': 'Recovery acceptance note'})
            response.raise_for_status()
        for number in (2, 3):
            files.write(sandbox.source_dir(project_id), 'backend/app/acceptance.py', f'VERSION = {number}\n')
            main.save_version(project_id, f'Acceptance version {number}')
        report = validation.run(project_id, 'acceptance', threading.Event(), browser_checks=True)
        assert report['status'] == 'passed'
        assert len(visual.listing(project_id)) == 2
        interaction = visual.capture(project_id, actions=[
            {'action': 'fill', 'selector': '[aria-label="New note"]', 'value': 'Browser interaction worked'},
            {'action': 'click', 'selector': 'button:has-text("Add note")', 'value': ''},
            {'action': 'visible', 'selector': 'article:has-text("Browser interaction worked")', 'value': ''}])
        assert interaction['status'] == 'passed'
        exported = recovery.create(project_id, 'disposable acceptance password')
        path, _ = recovery.export_path(project_id, exported['id'])
        imported = recovery.import_archive(path, 'disposable acceptance password')
        created_ids.append(imported['id'])
        versions = db.query('SELECT * FROM versions WHERE project_id=%s', (imported['id'],))
        assert len(versions) == 3
        recovered_url = sandbox.start(imported['id'])
        with httpx.Client(base_url=recovered_url, timeout=20, trust_env=False) as browser:
            notes = browser.get('/api/notes').json()
            assert any(item['text'] == 'Recovery acceptance note' for item in notes)
            assert any(item['text'] == 'Browser interaction worked' for item in notes)
        release = releases.bundle(project_id, report, report['source_digest'])
        release_root = tmp_path / 'release'
        with zipfile.ZipFile(io.BytesIO(release)) as archive:
            archive.extractall(release_root)  # our own path-validated bundle, not user input
        run(['bash', str(release_root / 'build-release.sh')], timeout=300)
        env_file = release_root / '.env'
        env_file.write_text(env_file.read_text().replace('APP_PORT=8080', 'APP_PORT=0'))
        settings = dict(line.split('=', 1) for line in env_file.read_text().splitlines() if '=' in line)
        release_name = settings['RELEASE_NAME']
        assert re.fullmatch(r'foundry-release-[0-9a-f]{8}', release_name)
        compose = ['docker', 'compose', '--project-directory', str(release_root), '-f', str(release_root / 'compose.yaml')]
        run([*compose, 'up', '-d', '--wait', '--wait-timeout', '150'], timeout=180)
        address = run([*compose, 'port', 'web', '8080']).strip()
        assert re.fullmatch(r'127\.0\.0\.1:\d+', address)
        with httpx.Client(base_url='http://' + address, timeout=20, trust_env=False) as browser:
            page = browser.get('/')
            assert page.status_code == 200 and '/@vite/client' not in page.text
            assert browser.get('/api/health').is_success
            assert browser.get('/api/notes').json() == []  # preview data is not deployed
    finally:
        if compose:
            run([*compose, 'down', '--volumes', '--timeout', '5'], timeout=60)
        for pid in created_ids:
            sandbox.command(pid, 'down', '--volumes', '--timeout', '5', timeout=60)
        if release_name and re.fullmatch(r'foundry-release-[0-9a-f]{8}', release_name):
            tag = settings.get('RELEASE_TAG', 'release')
            run(['docker', 'image', 'rm', release_name + '-web:' + tag, release_name + '-api:' + tag], timeout=30)
