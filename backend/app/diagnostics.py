"""Non-secret local readiness checks for support and first-run diagnosis."""
import platform
import shutil

import httpx

from . import config, db, dependencies, host, providers, visual
from .process import run


def command(name, argv):
    executable = shutil.which(argv[0])
    if not executable:
        return {'status': 'missing', 'detail': name + ' is not installed'}
    try:
        detail = run([executable, *argv[1:]], timeout=12, output_limit=1000).strip().splitlines()[0]
        return {'status': 'passed', 'detail': detail[:300]}
    except Exception as exc:
        return {'status': 'failed', 'detail': str(exc)[:300]}


def report():
    checks = {
        'python': {'status': 'passed', 'detail': platform.python_version()},
        'node': command('Node.js', ['node', '--version']),
        'docker': command('Docker', ['docker', 'version', '--format', '{{.Server.Version}}']),
        'compose': command('Docker Compose', ['docker', 'compose', 'version', '--short']),
        'github': command('GitHub CLI', ['gh', '--version']),
        'ocr': command('Tesseract OCR', ['tesseract', '--version']),
    }
    for name, image in {'web_image': 'local-foundry-web:2', 'api_image': 'local-foundry-api:2',
                        'accounts_image': dependencies.accounts_image(),
                        'database_image': 'postgres:17-bookworm', 'browser_image': visual.IMAGE}.items():
        checks[name] = command(image, ['docker', 'image', 'inspect', '--format', '{{.Id}}', image])
    try:
        db.query('SELECT 1 AS ok', one=True)
        checks['builder_database'] = {'status': 'passed', 'detail': 'connected'}
    except Exception as exc:
        checks['builder_database'] = {'status': 'failed', 'detail': type(exc).__name__ + ': connection failed'}
    try:
        probe = config.DATA / '.write-probe'
        probe.write_text('ok')
        probe.unlink()
        checks['storage'] = {'status': 'passed', 'detail': str(config.DATA)}
    except Exception as exc:
        checks['storage'] = {'status': 'failed', 'detail': type(exc).__name__ + ': write check failed'}
    local = {'status': 'not_configured', 'detail': 'Set LOCAL_MODEL to enable Local AI.'}
    if config.MODELS['local']:
        try:
            providers.key_for('local')
            with httpx.Client(timeout=3, trust_env=False) as client:
                response = client.get(config.LOCAL_API_BASE + '/models')
            available = [item.get('id') for item in response.json().get('data', [])] if response.is_success else []
            present = config.MODELS['local'] in available
            local = {'status': 'passed' if present else 'failed',
                     'detail': ('Configured model is listed. Tool calling must still be tested with a build.' if present else
                                'Configured LOCAL_MODEL was not listed by the loopback server. Download/load that exact model before disconnecting.')}
        except Exception as exc:
            local = {'status': 'failed', 'detail': str(exc)[:300]}
    checks['local_ai'] = local
    required = ['docker', 'compose', 'builder_database', 'storage', 'local_ai',
                'web_image', 'api_image', 'accounts_image', 'database_image', 'browser_image']
    platform_info = host.details()
    if platform_info['wsl']:
        supported = platform_info['wsl2'] and not host.windows_filesystem(config.DATA)
        checks['wsl_storage'] = {'status': 'passed' if supported else 'failed',
            'detail': 'WSL2 with Linux-side storage' if supported else 'Use WSL2 and keep state in the Linux filesystem; see WINDOWS.md.'}
        required.append('wsl_storage')
    blockers = [name for name in required if checks[name]['status'] != 'passed']
    disk = shutil.disk_usage(config.DATA)
    return {'platform': platform_info,
            'offline_only': config.OFFLINE_ONLY,
            'offline_readiness': {'ready': not blockers and config.OFFLINE_ONLY, 'blockers': blockers,
                'note': 'Preflight only. Prove disconnection by disabling the network and completing a local-model build. Additional project dependency images must also be cached.'},
            'disk_free_bytes': disk.free, 'checks': checks}
