"""Reviewed self-hosting bundles; never deploy or publish implicitly."""
import io
import hashlib
import json
import zipfile
import yaml

from . import config, dependencies, files, sandbox

ASSETS = ('frontend/Dockerfile', 'frontend/server.mjs', 'backend/Dockerfile',
          'compose.yaml', 'configure-release.py', 'build-release.sh', 'DEPLOY.md')
ACCOUNT_ASSETS = ('compose.public.yaml', 'compose.online.yaml', 'compose.monitoring.yaml',
                  'Caddyfile', 'configure-deployment.py', 'egress/Dockerfile', 'egress/proxy.py',
                  'monitoring/prometheus.yml', 'monitoring/rules.yml', 'monitoring/alertmanager.yml',
                  'ops.py', 'ops/crypto_stream.py', 'ops/external_monitor.py', 'OPERATIONS.md')


def bundle(project_id, validation, expected_digest):
    source = sandbox.source_dir(project_id)
    digest = files.digest(source)
    if digest != expected_digest or validation.get('status') != 'passed' or validation.get('source_digest') != digest:
        raise ValueError('Validate the current source and review its digest before preparing a release.')
    tags = dependencies.image_tags(source)
    from .profiles import get as get_profile
    profile = get_profile(source)
    if profile == 'accounts' and (validation.get('gate_version', 0) < 6 or not validation.get('browser_checks') or
            not {'Protected security contracts', 'Authenticated user journeys'} <= {item['name'] for item in validation.get('checks', []) if item.get('status') == 'passed'}):
        raise ValueError('Accounts releases require the protected security contracts and authenticated browser journeys on this source (v0.6+ gate).')
    content = files.export(source)
    # Imported/model-authored runtime files are never used as release infrastructure.
    for path in list(content):
        if path in {'compose.json', 'frontend/Dockerfile', 'backend/Dockerfile', 'backend/runtime.py'}:
            del content[path]
    assets = config.ROOT / 'release-template'
    for relative in ASSETS + (ACCOUNT_ASSETS if profile == 'accounts' else ()):
        path = assets / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError('A trusted release template file is missing or unsafe.')
        content[relative] = path.read_text()
    content['frontend/Dockerfile'] = content['frontend/Dockerfile'].replace('FOUNDRY_WEB_IMAGE', tags['web'])
    content['backend/Dockerfile'] = content['backend/Dockerfile'].replace('FOUNDRY_API_IMAGE', tags['api'])
    if profile == 'accounts':
        content['egress/Dockerfile'] = content['egress/Dockerfile'].replace('FOUNDRY_API_IMAGE', tags['api'])
        overlay = yaml.safe_load((assets / 'compose.accounts.yaml').read_text())
        compose = yaml.safe_load(content['compose.yaml'])
        compose['services']['api']['environment'] = overlay['services']['api']['environment']
        compose['services']['worker'] = overlay['services']['worker']
        content['compose.yaml'] = yaml.safe_dump(compose, sort_keys=False)
    content['backend/runtime.py'] = (config.ROOT / 'template/backend/runtime.py').read_text()
    content['.gitignore'] = content.get('.gitignore', '') + '\n.env\n.env.*\n.secrets/\n.ops/\n*.lfb\n*.dump\nruntime-images.tar\nrelease-images.tar\n'
    release_id = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    migrations = {path.split('/')[-1]: hashlib.sha256(value.encode()).hexdigest() for path, value in content.items() if path.startswith('backend/migrations/') and path.endswith('.sql')}
    file_hashes = {path: hashlib.sha256(value.encode()).hexdigest() for path, value in content.items()}
    content['release.json'] = json.dumps({'format': 1, 'builder_version': '0.11.0', 'release_id': release_id, 'file_hashes': file_hashes, 'migrations': migrations, 'profile': profile, 'source_digest': digest,
        'runtime_images': tags, 'validation': validation,
        'scope': 'Self-hosted Docker release. No cloud resources created. Security review required before public exposure.'}, indent=2)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, value in content.items():
            info = zipfile.ZipInfo(path)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if path.endswith('.sh') else 0o100644) << 16
            archive.writestr(info, value)
    return output.getvalue()
