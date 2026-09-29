"""Versioned acceptance report. Blocked checks never count as passed."""
import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['local','mac','windows','live'], default='local')
    parser.add_argument('--provider', choices=['local','anthropic','openai'], default='local')
    parser.add_argument('--budget', type=float, default=1.0)
    parser.add_argument('--output', default='acceptance-results')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    env = dict(os.environ)
    if args.mode == 'windows':
        env['FOUNDRY_CAPTURE_PLATFORM'] = 'windows'
    env['PYTHONPATH'] = str(ROOT/'backend') + os.pathsep + env.get('PYTHONPATH', '')

    def blocked(name, reason):
        checks.append({'name':name, 'status':'blocked', 'detail':reason})

    def run(name, command, cwd=ROOT, timeout=180, extra=None):
        start = time.monotonic()
        try:
            result = subprocess.run(command, cwd=cwd, env={**env, **(extra or {})}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            # Build/test commands must not print credential-bearing environment data.
            log = result.stdout.decode(errors='replace')
            for key in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','BUILDER_TOKEN','STRIPE_SECRET_KEY','RESEND_API_KEY'):
                if env.get(key):
                    log = log.replace(env[key], '[redacted]')
            filename = str(len(checks)+1)+'.log'
            (output/filename).write_text(log)
            checks.append({'name':name, 'status':'passed' if result.returncode == 0 else 'failed', 'seconds':round(time.monotonic()-start, 2), 'log':filename})
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append({'name':name, 'status':'failed', 'detail':type(exc).__name__})
            return False

    run('Unit and behavioral regression suite', [sys.executable, '-m', 'pytest', 'tests', '-q'], timeout=240)
    storage_url = env.get('FOUNDRY_TEST_DATABASE_URL', '').strip()
    if storage_url:
        run('PostgreSQL storage pass (builder and accounts kit)',
            [sys.executable, '-m', 'pytest', 'tests', '-q', '-k', 'postgres'], timeout=600)
    else:
        blocked('PostgreSQL storage pass (builder and accounts kit)',
                'Set FOUNDRY_TEST_DATABASE_URL to a scratch database (the user needs CREATEDB) to run the suite against real PostgreSQL.')
    for name, folder in [('Builder React production build','frontend'), ('Starter React production build','template/frontend')]:
        if (ROOT/folder/'node_modules').is_dir() and shutil.which('npm'):
            run(name, ['npm', 'run', 'build'], cwd=ROOT/folder)
        else:
            blocked(name, 'Install the locked frontend dependencies first.')
    if (ROOT/'template/frontend/node_modules').is_dir() and shutil.which('npm'):
        with tempfile.TemporaryDirectory(prefix='accounts-build-', dir=output) as temporary:
            target = Path(temporary)
            shutil.copytree(ROOT/'template/frontend', target, dirs_exist_ok=True, ignore=shutil.ignore_patterns('node_modules','dist'))
            shutil.copytree(ROOT/'kits/accounts/frontend', target, dirs_exist_ok=True)
            (target/'node_modules').symlink_to(ROOT/'template/frontend/node_modules', target_is_directory=True)
            run('Accounts React production build', ['npm','run','build'], cwd=target)
    else:
        blocked('Accounts React production build', 'Install the locked template frontend dependencies first.')
    if (ROOT/'frontend/node_modules').is_dir() and shutil.which('npm'):
        run('Frontend render smoke (App and extracted panels)', ['npm', 'run', 'smoke'], cwd=ROOT/'frontend', timeout=240)
    else:
        blocked('Frontend render smoke (App and extracted panels)', 'Install the locked builder frontend dependencies first.')
    # The UI capture doubles as the accessibility gate: it visits every primary
    # state with a real browser, so it is the only check that sees resolved CSS.
    def chrome_available():
        if os.environ.get('CHROME_PATH') and Path(os.environ['CHROME_PATH']).exists():
            return True
        mac = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        return mac.exists() or any(shutil.which(name) for name in ('google-chrome', 'chromium', 'chromium-browser'))

    if not (ROOT/'frontend/node_modules').is_dir() or not shutil.which('npm'):
        blocked('Accessibility scan (builder and accounts states)', 'Install the locked frontend dependencies first.')
    elif not (ROOT/'frontend/node_modules/axe-core').is_dir():
        blocked('Accessibility scan (builder and accounts states)', 'axe-core is missing; run npm --prefix frontend ci.')
    elif not chrome_available():
        blocked('Accessibility scan (builder and accounts states)',
                'Install Google Chrome or Chromium, or set CHROME_PATH, then rerun.')
    elif not (ROOT/'screenshots/a11y-baseline.builder.json').is_file():
        blocked('Accessibility scan (builder and accounts states)',
                'No baseline yet. Run node scripts/capture-ui.mjs --a11y-baseline (and --accounts) once, review it, then commit it.')
    else:
        # Each capture records its own pass/fail; a non-zero exit means new
        # findings outside the committed baseline. Detail is in the run's log and
        # in screenshots/*/accessibility.json.
        run('Accessibility scan (builder states)', ['node', 'scripts/capture-ui.mjs'], timeout=900)
        run('Accessibility scan (accounts states)', ['node', 'scripts/capture-ui.mjs', '--accounts'], timeout=900)
    # The mobile generator is checkable anywhere; compiling an APK or an IPA is not.
    run('Mobile wrapper generator', [sys.executable, '-m', 'pytest', 'tests/test_mobile.py', '-q'], timeout=180)
    run('App icons and store screenshots',
        [sys.executable, '-m', 'pytest', 'tests/test_mobile_assets.py', '-q'], timeout=300)
    android_sdk = any(os.environ.get(name) and Path(os.environ[name]).is_dir()
                      for name in ('ANDROID_HOME', 'ANDROID_SDK_ROOT'))
    if android_sdk and shutil.which('java'):
        blocked('Signed Android build (APK/AAB)',
                'SDK present. Build a testing APK from the Mobile tab and verify it on a device. For a Play release, run '
                './gradlew bundleRelease with your upload key; signing keys are never supplied here.')
    else:
        blocked('Signed Android build (APK/AAB)',
                'No Android SDK on this host. Install it, set ANDROID_HOME, then follow MOBILE.md.')
    blocked('Signed iOS build (IPA)',
            'Use a Mac or macOS CI runner with signing credentials; see MOBILE.md.')
    wsl2 = platform.system() == 'Linux' and 'wsl2' in platform.release().lower()
    if args.mode == 'windows' and wsl2:
        if not (ROOT/'frontend/node_modules').is_dir() or not shutil.which('npm'):
            blocked('Windows/WSL UI capture', 'Install the locked frontend dependencies first.')
        elif not (ROOT/'frontend/node_modules/axe-core').is_dir():
            blocked('Windows/WSL UI capture', 'axe-core is missing; run npm --prefix frontend ci.')
        elif not chrome_available():
            blocked('Windows/WSL UI capture', 'Install Linux Chrome/Chromium in WSL or set CHROME_PATH.')
        else:
            run('Windows/WSL builder UI and accessibility capture', ['node', 'scripts/capture-ui.mjs'], timeout=900,
                extra={'FOUNDRY_CAPTURE_PLATFORM':'windows'})
            run('Windows/WSL accounts UI and accessibility capture', ['node', 'scripts/capture-ui.mjs', '--accounts'], timeout=900,
                extra={'FOUNDRY_CAPTURE_PLATFORM':'windows'})
    elif args.mode != 'windows':
        if platform.system() != 'Darwin':
            blocked('macOS smoke and UI capture', 'Requires the target Mac, Docker Desktop and Google Chrome.')
        elif args.mode == 'local':
            blocked('macOS smoke and UI capture', 'Run --mode mac on the target Mac.')
        else:
            run('macOS smoke and UI capture', ['bash', 'scripts/mac-smoke-test.sh'], timeout=1200)
    if args.mode == 'windows' and wsl2:
        checks.append({'name':'WSL2 runtime', 'status':'passed', 'detail':platform.release()})
    else:
        blocked('Windows 11 / WSL2 runtime and UI capture', 'Run Windows.ps1 Start and Windows.ps1 Test on the target Windows 11 laptop.')
    blocked('Native launcher, preview access and physically disconnected restart', 'Follow WINDOWS.md on Windows, or the packaged-app procedure on Mac: disable networking, restart, edit with a cached local model and verify preview data survives.')
    docker = bool(shutil.which('docker'))
    if docker and (args.mode in {'mac','live'} or args.mode == 'windows' and wsl2):
        run('Real PostgreSQL, browser journeys, recovery and release', [sys.executable,'-m','pytest','tests/test_live_acceptance.py','-q'],
            timeout=1200, extra={'FOUNDRY_LIVE_DOCKER':'1'})
    else:
        blocked('Real PostgreSQL, browser journeys, recovery and release', 'Docker unavailable or real Docker acceptance not selected; run --mode mac or --mode windows on the target host.')
    if args.mode == 'live' and docker:
        run('Real model Accounts build', [sys.executable,'scripts/live-model-smoke.py','--provider',args.provider,'--profile','accounts','--budget',str(args.budget),'--confirm'], timeout=1300)
    else:
        blocked('Real model Accounts build', 'Requires a running builder and configured model. --mode live authorizes model calls; cloud providers may charge.')
    blocked('Real Stripe checkout, email delivery and outbound webhook', 'Requires your staging/test provider accounts and a reachable HTTPS app. Follow PROVIDER-ACCEPTANCE.md; no provider credentials supplied to this harness.')
    blocked('Deployment-host staging, encrypted backup restore and external alert delivery', 'Run the exported OPERATIONS.md acceptance on the actual deployment and independent monitoring hosts.')
    report = {'version':'0.11.0', 'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'platform':platform.system(),
              'mode':args.mode, 'status':'failed' if any(c['status']=='failed' for c in checks) else 'incomplete' if any(c['status']=='blocked' for c in checks) else 'passed',
              'checks':checks, 'scope':'Local tests and builds are not Windows, Docker, live provider, mobile-device or deployment acceptance. PostgreSQL storage coverage requires the explicit scratch database.'}
    (output/'acceptance.json').write_text(json.dumps(report, indent=2))
    (output/'ACCEPTANCE.md').write_text('# Local Foundry v0.11.0 acceptance\n\nOverall: **'+report['status']+'**\n\n'+
        '\n'.join('- **'+c['status']+'** — '+c['name']+(': '+c['detail'] if 'detail' in c else '') for c in checks)+'\n')
    print(json.dumps(report, indent=2))
    return 1 if report['status']=='failed' else 2 if report['status']=='incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
