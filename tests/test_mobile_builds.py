"""Native compilers are stubbed; real process cancellation and artifact guards run."""
import os
import json
import plistlib
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile

import pytest

from app import config, db, files, mobile_builds as mobile, sandbox
from conftest import wait_run


def body(project_id, target='apk'):
    return {'target': target, 'origin': 'https://app.example.com', 'name': 'Reading Room',
            'app_id': 'com.example.readingroom', 'version': '1.2.3', 'build_number': 7,
            'team_id': 'ABCDEFGHIJ', 'export_method': 'debugging', 'allow_network': True,
            'source_digest': files.digest(sandbox.source_dir(project_id))}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(config, 'OFFLINE_ONLY', False)
    monkeypatch.setattr(mobile, 'capabilities', lambda: {key: {'available': True, 'blockers': []} for key in ('apk', 'aab', 'ipa')})


def fake_compile(work, data, cancelled, deadline, log_path, phase):
    work.mkdir()
    output = work / ('output.' + data['target'])
    phase('Compiling test fixture')
    with zipfile.ZipFile(output, 'w') as archive:
        if data['target'] == 'apk':
            archive.writestr('AndroidManifest.xml', 'test manifest')
            archive.writestr('classes.dex', b'test fixture, not a real APK')
        elif data['target'] == 'aab':
            archive.writestr('BundleConfig.pb', b'test bundle config')
            archive.writestr('base/manifest/AndroidManifest.xml', b'test manifest')
            archive.writestr('META-INF/UPLOAD.RSA', b'fixture, not a real signature')
        else:
            archive.writestr('Payload/App.app/Info.plist', plistlib.dumps({'CFBundleIdentifier': data['app_id']}))
            archive.writestr('Payload/App.app/_CodeSignature/CodeResources', b'test fixture, not a real signature')
    return output


@pytest.mark.parametrize('target', ['apk', 'aab', 'ipa'])
def test_build_history_authenticated_download_and_source_preservation(client, enabled, monkeypatch, target, tmp_path):
    pid = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']
    data = bundle_body(pid, tmp_path) if target == 'aab' else body(pid, target)
    monkeypatch.setattr(mobile, 'compile_native', fake_compile)
    result = wait_run(client, client.post(f'/api/projects/{pid}/mobile/builds', json=data))
    assert result['status'] == 'completed'
    history = client.get(f'/api/projects/{pid}/mobile/builds').json()
    assert len(history) == 1 and history[0]['status'] == 'completed'
    item = history[0]
    assert item['bytes'] > 0 and len(item['sha256']) == 64
    assert not (mobile.directory(pid, item['id']) / 'work').exists()
    download = f'/api/projects/{pid}/mobile/builds/{item["id"]}/download'
    response = client.get(download)
    assert response.status_code == 200
    assert item['filename'] in response.headers['content-disposition']
    assert len(response.content) == item['bytes']
    assert client.get(download, headers={'Authorization': ''}).status_code == 401
    assert client.get(download, headers={'Origin': 'https://evil.example.com'}).status_code == 403
    other = client.post('/api/projects', json={'name': 'Other'}).json()['id']
    assert client.get(download.replace(pid, other)).status_code == 400
    assert files.digest(sandbox.source_dir(pid)) == data['source_digest']
    path = mobile.directory(pid, item['id']) / ('app.' + target)
    path.write_bytes(b'tampered')
    assert client.get(download).status_code == 400


def test_preflight_denies_offline_unapproved_missing_tools_and_stale_source(client, enabled, monkeypatch):
    pid = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']
    data = body(pid)
    url = f'/api/projects/{pid}/mobile/builds'
    assert client.post(url, json={**data, 'allow_network': False}).status_code == 400
    monkeypatch.setattr(config, 'OFFLINE_ONLY', True)
    assert client.post(url, json=data).status_code == 400
    monkeypatch.setattr(config, 'OFFLINE_ONLY', False)
    assert client.post(url, json={**data, 'source_digest': '0' * 64}).status_code == 400
    assert client.post(url, json={**data, 'target': 'ipa', 'team_id': ''}).status_code == 400
    monkeypatch.setattr(mobile, 'capabilities', lambda: {'apk': {'blockers': ['Install Android SDK']}})
    assert 'Install Android SDK' in client.post(url, json=data).json()['detail']
    assert client.get(url).json() == []


@pytest.mark.parametrize('mode', ['failure', 'invalid-output', 'cancel'])
def test_failure_and_cancellation_never_publish_artifacts(client, enabled, monkeypatch, mode):
    pid = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']
    def compile(work, data, cancelled, deadline, log_path, phase):
        work.mkdir()
        if mode == 'failure':
            raise RuntimeError('compiler failed')
        if mode == 'cancel':
            cancelled.set()
            mobile.check_cancel(cancelled)
        path = work / 'bad.apk'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('source.txt', 'not an APK')
        return path
    monkeypatch.setattr(mobile, 'compile_native', compile)
    result = wait_run(client, client.post(f'/api/projects/{pid}/mobile/builds', json=body(pid)))
    item = client.get(f'/api/projects/{pid}/mobile/builds').json()[0]
    assert result['status'] == item['status'] == ('cancelled' if mode == 'cancel' else 'failed')
    assert client.get(f'/api/projects/{pid}/mobile/builds/{item["id"]}/download').status_code == 400
    assert not (mobile.directory(pid, item['id']) / 'work').exists()


def test_restart_marks_unfinished_mobile_build_interrupted(client):
    pid = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']
    rid = 'd' * 32
    directory = mobile.directory(pid, rid)
    directory.mkdir(parents=True)
    mobile.write_record(directory, {'id': rid, 'project_id': pid, 'status': 'running', 'created_at': db.now()})
    assert mobile.listing(pid)[0]['status'] == 'interrupted'


def test_download_rejects_linked_artifacts(client, enabled, monkeypatch, tmp_path):
    pid = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']
    monkeypatch.setattr(mobile, 'compile_native', fake_compile)
    wait_run(client, client.post(f'/api/projects/{pid}/mobile/builds', json=body(pid)))
    item = mobile.listing(pid)[0]
    path = mobile.directory(pid, item['id']) / 'app.apk'
    copy = tmp_path / 'private.apk'
    path.rename(copy)
    path.symlink_to(copy)
    with pytest.raises(ValueError, match='linked'):
        mobile.artifact(pid, item['id'])


def test_build_environment_excludes_provider_secrets_and_injected_flags(monkeypatch, tmp_path):
    for key in ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'BUILDER_TOKEN', 'NODE_OPTIONS', 'JAVA_TOOL_OPTIONS', 'NPM_TOKEN', 'GRADLE_OPTS'):
        monkeypatch.setenv(key, 'must-not-inherit')
    work = tmp_path / 'job/work'
    work.mkdir(parents=True)
    env = mobile.build_environment(work)
    assert 'must-not-inherit' not in env.values()
    assert env['GRADLE_USER_HOME'] == str(work / '.gradle-home')
    assert env['npm_config_ignore_scripts'] == 'true'
    assert env['npm_config_userconfig'] != env['npm_config_globalconfig']


def test_cancel_terminates_real_child_process(tmp_path):
    cancel = threading.Event()
    timer = threading.Timer(.4, cancel.set)
    timer.start()
    pidfile = tmp_path / 'pid'
    try:
        with pytest.raises(InterruptedError, match='cancelled'):
            mobile.command([sys.executable, '-c', 'import os,time; from pathlib import Path; '
                            f'Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(30)'],
                           tmp_path, mobile.build_environment(), cancel, time.monotonic() + 10, tmp_path / 'log')
    finally:
        timer.cancel()
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, signal.SIGCONT)


def test_windows_ipa_capability_reports_mac_requirement(monkeypatch):
    monkeypatch.setattr(mobile.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(mobile, 'version', lambda *args: 26)
    result = mobile.capabilities()
    assert not result['ipa']['available']
    assert any('macOS' in reason for reason in result['ipa']['blockers'])


def test_mobile_cancel_endpoint_and_project_lock(client, enabled, monkeypatch):
    pid = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']
    entered = threading.Event()
    def compile(work, data, cancelled, *args):
        entered.set()
        if not cancelled.wait(3):
            raise AssertionError('Cancellation did not reach the native worker.')
        mobile.check_cancel(cancelled)
    monkeypatch.setattr(mobile, 'compile_native', compile)
    response = client.post(f'/api/projects/{pid}/mobile/builds', json=body(pid))
    assert response.status_code == 202 and entered.wait(2)
    assert client.post(f'/api/projects/{pid}/mobile/builds', json=body(pid)).status_code == 409
    assert client.post('/api/runs/' + response.json()['run_id'] + '/cancel', json={}).status_code == 200
    assert wait_run(client, response)['status'] == 'cancelled'


@pytest.mark.parametrize('target', ['apk', 'ipa'])
def test_native_pipeline_generates_hardens_signs_and_exports(tmp_path, monkeypatch, target):
    from test_mobile import fake_android_project
    sdk = tmp_path / 'sdk'
    signer = sdk / 'build-tools/36.0.0/apksigner'
    signer.parent.mkdir(parents=True)
    signer.touch()
    monkeypatch.setattr(mobile, 'android_sdk', lambda: sdk)
    work = tmp_path / 'job/work'
    calls = []
    def run(argv, cwd, env, cancelled, deadline, log_path):
        argv = [str(arg) for arg in argv]
        calls.append(argv)
        if 'add' in argv and target == 'apk':
            fake_android_project(work)
        if 'add' in argv and target == 'ipa':
            info = work / 'ios/App/App/Info.plist'
            info.parent.mkdir(parents=True)
            info.write_bytes(plistlib.dumps({'CFBundleIdentifier': 'com.example.app'}))
        if 'assembleDebug' in argv:
            assert 'versionCode 7' in (work / 'android/app/build.gradle').read_text()
        if 'archive' in argv:
            (work / 'App.xcarchive/Products/Applications/App.app').mkdir(parents=True)
        if '-exportArchive' in argv:
            options = plistlib.loads((work / 'ExportOptions.plist').read_bytes())
            assert options['destination'] == 'export' and options['teamID'] == 'ABCDEFGHIJ'
            (work / 'export').mkdir()
            (work / 'export/App.ipa').write_bytes(b'test export')
    monkeypatch.setattr(mobile, 'command', run)
    data = {'name': 'App', 'app_id': 'com.example.app', 'origin': 'https://app.example.com',
            'version': '1.2.3', 'target': target, 'build_number': 7,
            'team_id': 'ABCDEFGHIJ', 'export_method': 'debugging'}
    output = mobile.compile_native(work, data, threading.Event(), time.monotonic() + 20, tmp_path / 'log', lambda _: None)
    assert output.suffix == '.' + target
    package = json.loads((work / 'package.json').read_text())
    assert package['scripts'] == {} and package['dependencies']['@capacitor/core'] == '8.5.2'
    assert '--ignore-scripts' in calls[0]
    assert any('verify' in call or '--verify' in call for call in calls)


# --- Play Store app bundle -------------------------------------------------
# A debug APK cannot be published, so the AAB path is the one that actually
# reaches Play. It carries the upload key, which is the most sensitive material
# this tool touches: these check it is validated, kept out of argv, kept out of
# the persisted record, and scrubbed from the build log.

def keystore(tmp_path, magic=b'\xfe\xed\xfe\xed', name='upload.jks'):
    path = tmp_path / name
    path.write_bytes(magic + b'0' * 512)
    return path


def bundle_body(project_id, tmp_path, **overrides):
    data = body(project_id, 'aab')
    data.update(keystore_path=str(keystore(tmp_path)), key_alias='upload',
                store_password='storepass', key_password='keypass')
    data.update(overrides)
    return data


def test_bundle_requires_a_real_keystore(client, enabled, tmp_path):
    project_id = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']
    def refused(**overrides):
        response = client.post(f'/api/projects/{project_id}/mobile/builds',
                               json=bundle_body(project_id, tmp_path, **overrides))
        assert response.status_code == 400, response.text
        return response.json()['detail']

    assert 'full path' in refused(keystore_path='upload.jks')
    assert 'No keystore file' in refused(keystore_path=str(tmp_path / 'absent.jks'))
    # A pointer at an arbitrary host file must not reach Gradle.
    plain = tmp_path / 'notes.txt'
    plain.write_text('this is not a keystore')
    assert 'not a Java keystore' in refused(keystore_path=str(plain))
    link = tmp_path / 'linked.jks'
    link.symlink_to(keystore(tmp_path, name='real.jks'))
    assert 'symbolic link' in refused(keystore_path=str(link))
    assert 'alias' in refused(key_alias='bad alias!')
    assert 'passwords' in refused(store_password='short')


def test_pkcs12_keystore_is_accepted(tmp_path):
    data = {'keystore_path': str(keystore(tmp_path, magic=b'\x30\x82', name='upload.p12')),
            'key_alias': 'upload', 'store_password': 'storepass', 'key_password': ''}
    checked = mobile.validate_keystore(data)
    # An omitted key password falls back to the store password, as keytool does.
    assert checked['key_password'] == 'storepass'


def test_signing_material_never_reaches_the_record_or_the_log(client, enabled, monkeypatch, tmp_path):
    project_id = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']

    def compile_leaking_secrets(work, data, cancelled, deadline, log_path, phase):
        # Emulate a build tool echoing its configuration, which Gradle can do.
        mobile.command([sys.executable, '-c', 'print("storePassword=storepass keyPassword=keypass")'],
                       work.parent, {}, cancelled, deadline, log_path,
                       (data['store_password'], data['key_password']))
        work.mkdir(parents=True, exist_ok=True)
        output = work / 'app-release.aab'
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('BundleConfig.pb', 'x')
            archive.writestr('base/manifest/AndroidManifest.xml', 'x')
            archive.writestr('META-INF/UPLOAD.RSA', 'x')
        return output

    monkeypatch.setattr(mobile, 'compile_native', compile_leaking_secrets)
    started = client.post(f'/api/projects/{project_id}/mobile/builds',
                          json=bundle_body(project_id, tmp_path))
    assert started.status_code == 202, started.text
    assert wait_run(client, started)['status'] == 'completed'
    build = client.get(f'/api/projects/{project_id}/mobile/builds').json()[0]

    stored = json.dumps(build)
    for secret in ('storepass', 'keypass'):
        assert secret not in stored, 'a signing password reached the persisted build record'
    assert build['key_alias'] == 'upload', 'the alias is not secret and identifies the signing key'
    log = client.get(f"/api/projects/{project_id}/mobile/builds/{build['id']}/log").json()['log']
    assert 'storepass' not in log and 'keypass' not in log
    assert '[redacted signing secret]' in log
    assert build['filename'].endswith('-release.aab')


def test_bundle_pipeline_signs_with_the_upload_key_and_verifies_it(tmp_path, monkeypatch):
    from test_mobile import fake_android_project
    sdk = tmp_path / 'sdk'
    (sdk / 'build-tools/36.0.0').mkdir(parents=True)
    (sdk / 'build-tools/36.0.0/apksigner').touch()
    monkeypatch.setattr(mobile, 'android_sdk', lambda: sdk)
    work = tmp_path / 'job/work'
    calls, environments = [], []

    def run(argv, cwd, env, cancelled, deadline, log_path, secrets=()):
        argv = [str(arg) for arg in argv]
        calls.append(argv)
        environments.append(dict(env))
        if 'add' in argv:
            assert argv[-1] == 'android', 'AAB must generate the Android platform'
            fake_android_project(work)
        if 'sync' in argv:
            assert argv[-1] == 'android'
        if 'bundleRelease' in argv:
            gradle = (work / 'android/app/build.gradle').read_text()
            assert "apply from: 'signing.gradle'" in gradle
            assert 'versionCode 7' in gradle
            signing = (work / 'android/app/signing.gradle').read_text()
            # The passwords must be read from the environment, not written into a file.
            assert 'System.getenv("FOUNDRY_STORE_PASSWORD")' in signing
            assert data['store_password'] not in signing and data['key_password'] not in signing
            output = work / 'android/app/build/outputs/bundle/release/app-release.aab'
            output.parent.mkdir(parents=True)
            output.write_bytes(b'bundle')
    monkeypatch.setattr(mobile, 'command', run)

    data = {'name': 'App', 'app_id': 'com.example.app', 'origin': 'https://app.example.com',
            'version': '1.2.3', 'target': 'aab', 'build_number': 7,
            'keystore_path': str(keystore(tmp_path)), 'key_alias': 'upload',
            'store_password': 'bundle-store-fixture-secret', 'key_password': 'bundle-key-fixture-secret'}
    output = mobile.compile_native(work, data, threading.Event(), time.monotonic() + 20,
                                   tmp_path / 'log', lambda _: None)
    assert output.name == 'app-release.aab'
    assert any('bundleRelease' in call for call in calls), 'a Play upload needs a bundle, not assembleDebug'
    assert not any('assembleDebug' in call for call in calls)
    # jarsigner verifies bundles; apksigner cannot read one.
    assert any(call[0] == 'jarsigner' and '-verify' in call for call in calls)
    verification = next(call for call in calls if call[0] == 'jarsigner')
    assert '-strict' in verification
    assert verification[verification.index('-keystore') + 1] == data['keystore_path']
    assert verification[verification.index('-storepass:env') + 1] == 'FOUNDRY_STORE_PASSWORD'
    assert verification[-1] == 'upload'
    flat = ' '.join(' '.join(call) for call in calls)
    for secret in (data['store_password'], data['key_password']):
        assert secret not in flat, '/proc/<pid>/cmdline is world-readable; passwords must go in the environment'
    signing_env = [env for env in environments if 'FOUNDRY_STORE_PASSWORD' in env]
    assert signing_env and signing_env[-1]['FOUNDRY_KEY_ALIAS'] == 'upload'


@pytest.mark.parametrize('names,valid', [
    ({'BundleConfig.pb', 'base/manifest/AndroidManifest.xml', 'META-INF/UPLOAD.RSA'}, True),
    # An unsigned bundle is rejected by Play, so it must not be offered for download.
    ({'BundleConfig.pb', 'base/manifest/AndroidManifest.xml'}, False),
    ({'AndroidManifest.xml', 'classes.dex', 'META-INF/UPLOAD.RSA'}, False),
])
def test_only_a_signed_bundle_counts_as_an_artifact(tmp_path, names, valid):
    path = tmp_path / 'app.aab'
    with zipfile.ZipFile(path, 'w') as archive:
        for name in names:
            archive.writestr(name, 'x')
    if valid:
        mobile.inspect_artifact(path, 'aab')
    else:
        with pytest.raises(ValueError):
            mobile.inspect_artifact(path, 'aab')


def test_bundle_capability_requires_jarsigner(monkeypatch):
    monkeypatch.setattr(config, 'OFFLINE_ONLY', False)
    monkeypatch.setattr(mobile, 'android_sdk', lambda: None)
    monkeypatch.setattr(mobile.shutil, 'which', lambda name: None if name == 'jarsigner' else '/usr/bin/' + name)
    blockers = ' '.join(mobile.capabilities()['aab']['blockers'])
    assert 'jarsigner' in blockers


@pytest.fixture(scope='module')
def real_upload_key(tmp_path_factory):
    """Disposable keys and a real verifier; no Android SDK or user signing files."""
    keytool = shutil.which('keytool')
    signer = shutil.which('jarsigner')
    java = shutil.which('java')
    if not keytool or not (signer or java):
        pytest.skip('A JDK is required for real upload-signature regression checks.')
    signer = [signer] if signer else [java, '-m', 'jdk.jartool/sun.security.tools.jarsigner.Main']
    if subprocess.run([*signer, '-help'], capture_output=True, timeout=15).returncode:
        pytest.skip('The JDK jarsigner module is unavailable.')
    folder = tmp_path_factory.mktemp('upload-signature-fixture')
    path = folder / 'upload.p12'
    password = 'disposable-fixture-password'
    env = {**mobile.build_environment(), 'FOUNDRY_STORE_PASSWORD': password}
    for alias in ('upload', 'other'):
        result = subprocess.run([keytool, '-genkeypair', '-keystore', str(path), '-alias', alias,
                                 '-storetype', 'PKCS12', '-keyalg', 'RSA', '-keysize', '2048',
                                 '-validity', '10000', '-dname', 'CN=Local Foundry Test ' + alias,
                                 '-storepass:env', 'FOUNDRY_STORE_PASSWORD', '-noprompt'],
                                env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    yield path, password, signer
    path.unlink(missing_ok=True)


@pytest.mark.parametrize('mode', ['valid', 'unsigned', 'unsigned-entry', 'tampered', 'wrong-key'])
def test_bundle_verifier_accepts_only_intact_selected_upload_signature(
        tmp_path, monkeypatch, real_upload_key, mode):
    """Run production verification on a signed ZIP, stubbing only native generation.

    This is a cryptographic regression, not proof of a compiled/distributable AAB.
    """
    from test_mobile import fake_android_project
    keystore_path, password, signer = real_upload_key
    work = tmp_path / 'job/work'
    real_command = mobile.command
    monkeypatch.setattr(mobile, 'android_sdk', lambda: None)

    def run(argv, cwd, env, cancelled, deadline, log_path, secrets=()):
        argv = [str(arg) for arg in argv]
        if 'add' in argv:
            assert argv[-1] == 'android'
            fake_android_project(work)
        elif 'bundleRelease' in argv:
            output = work / 'android/app/build/outputs/bundle/release/app-release.aab'
            output.parent.mkdir(parents=True)
            with zipfile.ZipFile(output, 'w') as archive:
                archive.writestr('BundleConfig.pb', b'fixture, not a native app')
                archive.writestr('base/manifest/AndroidManifest.xml', b'fixture manifest')
            if mode != 'unsigned':
                signed = subprocess.run([*signer, '-keystore', str(keystore_path),
                                         '-storepass:env', 'FOUNDRY_STORE_PASSWORD', str(output),
                                         'other' if mode == 'wrong-key' else 'upload'],
                                        env=env, capture_output=True, text=True, timeout=30)
                assert signed.returncode == 0, signed.stderr
            if mode == 'tampered':
                with zipfile.ZipFile(output) as archive:
                    entries = {name: archive.read(name) for name in archive.namelist()}
                entries['BundleConfig.pb'] = b'changed after signing'
                with zipfile.ZipFile(output, 'w') as archive:
                    for name, content in entries.items():
                        archive.writestr(name, content)
            if mode == 'unsigned-entry':
                with zipfile.ZipFile(output, 'a') as archive:
                    archive.writestr('base/extra.txt', b'added without signing')
        elif argv[0] == 'jarsigner':
            return real_command([*signer, *argv[1:]], cwd, env, cancelled, deadline, log_path, secrets)

    monkeypatch.setattr(mobile, 'command', run)
    data = {'name': 'App', 'app_id': 'com.example.app', 'origin': 'https://app.example.com',
            'version': '1.2.3', 'target': 'aab', 'build_number': 7,
            'keystore_path': str(keystore_path), 'key_alias': 'upload',
            'store_password': password, 'key_password': password}
    args = (work, data, threading.Event(), time.monotonic() + 60, tmp_path / 'log', lambda _: None)
    if mode == 'valid':
        output = mobile.compile_native(*args)
        mobile.inspect_artifact(output, 'aab')
    elif mode == 'unsigned':
        # Some JDKs return success for a wholly unsigned ZIP. The artifact guard
        # used by execute() must still refuse it before publishing a download.
        output = mobile.compile_native(*args)
        with pytest.raises(ValueError, match='build output'):
            mobile.inspect_artifact(output, 'aab')
    else:
        with pytest.raises(RuntimeError):
            mobile.compile_native(*args)
    assert password not in (tmp_path / 'log').read_text()


def test_build_generates_real_icons_and_refuses_a_bad_source(client, enabled, tmp_path, monkeypatch):
    """A build with an icon source must carry the app's own branding; without one it
    still builds, because a test APK does not need it."""
    from PIL import Image
    from test_mobile import fake_android_project
    sdk = tmp_path / 'sdk'
    (sdk / 'build-tools/36.0.0').mkdir(parents=True)
    (sdk / 'build-tools/36.0.0/apksigner').touch()
    monkeypatch.setattr(mobile, 'android_sdk', lambda: sdk)
    logo = tmp_path / 'logo.png'
    Image.new('RGBA', (1024, 1024), (35, 64, 42, 255)).save(logo)
    work = tmp_path / 'job/work'

    def run(argv, cwd, env, cancelled, deadline, log_path, secrets=()):
        argv = [str(arg) for arg in argv]
        if 'add' in argv:
            fake_android_project(work)
        if 'assembleDebug' in argv:
            icon = work / 'android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png'
            assert icon.is_file(), 'the artifact would ship Capacitor placeholder icons'
            with Image.open(icon) as image:
                assert image.size == (192, 192)
            output = work / 'android/app/build/outputs/apk/debug/app-debug.apk'
            output.parent.mkdir(parents=True)
            output.write_bytes(b'apk')
    monkeypatch.setattr(mobile, 'command', run)
    data = {'name': 'App', 'app_id': 'com.example.app', 'origin': 'https://app.example.com',
            'version': '1.2.3', 'target': 'apk', 'build_number': 7,
            'icon_source': str(logo), 'icon_background': '#101510'}
    mobile.compile_native(work, data, threading.Event(), time.monotonic() + 30,
                          tmp_path / 'log', lambda _: None)
    assert (work / '.foundry-icons.json').is_file()

    project_id = client.post('/api/projects', json={'name': 'Mobile'}).json()['id']
    body_with = body(project_id)
    body_with['icon_source'] = str(tmp_path / 'not-an-image.txt')
    (tmp_path / 'not-an-image.txt').write_text('nope')
    refused = client.post(f'/api/projects/{project_id}/mobile/builds', json=body_with)
    assert refused.status_code == 400
    assert 'image' in refused.json()['detail'].lower()
