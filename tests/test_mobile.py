"""The mobile wrapper cannot be built here (no Android SDK, and an IPA needs macOS),
so these cover what can go wrong before a build: configuration that would ship an
insecure app, and hardening that a `cap add` silently discarded.
"""
import importlib.util
import json
from xml.etree import ElementTree

import pytest

from app import config

spec = importlib.util.spec_from_file_location('foundry_mobile', config.ROOT / 'scripts/mobile.py')
mobile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile)


def generate(tmp_path, **overrides):
    args = mobile.argparse.Namespace(
        origin='https://app.example.com', name='Reading Room', app_id='com.example.readingroom',
        version='1.0.0', output=str(tmp_path / 'mobile-build'), force=False, debuggable=False)
    for key, value in overrides.items():
        setattr(args, key, value)
    mobile.do_init(args)
    return tmp_path / 'mobile-build'


@pytest.mark.parametrize('origin', [
    'http://app.example.com',          # cookies in plaintext
    'https://localhost:8765',          # works only on the developer's machine
    'https://127.0.0.1',
    'https://192.168.1.10',            # no certificate, no review
    'https://app.example.com/path',    # an origin has no path
    'https://user:pw@app.example.com',
    'ftp://app.example.com',
    '',
])
def test_unsafe_origins_are_refused(origin):
    with pytest.raises(mobile.InvalidInput):
        mobile.validate_origin(origin)


def test_https_origin_is_normalised():
    assert mobile.validate_origin('https://app.example.com/') == 'https://app.example.com'
    assert mobile.validate_origin('https://app.example.com:8443') == 'https://app.example.com:8443'
    assert mobile.validate_origin('https://app.example.com:443') == 'https://app.example.com'


@pytest.mark.parametrize('app_id', [
    'readingroom',            # needs at least two segments
    'com.example.',
    '1com.example',           # segment must start with a letter
    'com.example.reading-room',
    'com.new.app',            # 'new' is a Java keyword; Gradle fails late on this
    'com.class.app',
    '',
])
def test_invalid_app_ids_are_refused(app_id):
    with pytest.raises(mobile.InvalidInput):
        mobile.validate_app_id(app_id)


def test_valid_app_id_is_accepted():
    assert mobile.validate_app_id('com.example.readingroom') == 'com.example.readingroom'
    assert mobile.validate_app_id('uk.co.example.app2') == 'uk.co.example.app2'


def test_generated_config_locks_the_webview_to_one_host(tmp_path):
    project = generate(tmp_path)
    config_json = json.loads((project / 'capacitor.config.json').read_text())
    server = config_json['server']
    assert server['url'] == 'https://app.example.com'
    # A wildcard here would let a redirect carry the native bridge to another site.
    assert server['allowNavigation'] == ['app.example.com']
    assert server['cleartext'] is False
    assert config_json['android']['allowMixedContent'] is False
    assert config_json['android']['webContentsDebuggingEnabled'] is False
    assert config_json['ios']['webContentsDebuggingEnabled'] is False
    assert config_json['plugins'] == {}, 'every plugin is reachable from remote pages'


def test_offline_page_is_generated_and_points_at_the_app(tmp_path):
    project = generate(tmp_path)
    page = (project / 'www' / 'index.html').read_text()
    assert 'https://app.example.com' in page
    assert 'Reading Room' in page
    assert '__APP_NAME__' not in page and '__ORIGIN__' not in page
    # A blank screen on a bad connection is a common review rejection.
    assert 'Try again' in page


def test_check_passes_a_fresh_project_and_fails_a_tampered_one(tmp_path, capsys):
    project = generate(tmp_path)
    args = mobile.argparse.Namespace(output=str(project))
    assert mobile.do_check(args) == 0

    config_json = json.loads((project / 'capacitor.config.json').read_text())
    config_json['server']['allowNavigation'] = ['*']
    (project / 'capacitor.config.json').write_text(json.dumps(config_json))
    assert mobile.do_check(args) == 1
    assert 'wildcard' in capsys.readouterr().err


def test_check_rejects_debugging_left_enabled(tmp_path, capsys):
    project = generate(tmp_path, debuggable=True)
    assert mobile.do_check(mobile.argparse.Namespace(output=str(project))) == 1
    assert 'webContentsDebuggingEnabled' in capsys.readouterr().err


def test_check_rejects_a_cleartext_downgrade(tmp_path, capsys):
    project = generate(tmp_path)
    config_json = json.loads((project / 'capacitor.config.json').read_text())
    config_json['server']['cleartext'] = True
    (project / 'capacitor.config.json').write_text(json.dumps(config_json))
    assert mobile.do_check(mobile.argparse.Namespace(output=str(project))) == 1
    assert 'cleartext' in capsys.readouterr().err


def fake_android_project(project):
    """The parts of `npx cap add android` that hardening touches, as the Capacitor
    template actually emits them."""
    app = project / 'android' / 'app'
    (app / 'src/main/res/xml').mkdir(parents=True, exist_ok=True)
    (app / 'build.gradle').write_text(
        'android {\n    defaultConfig {\n        applicationId "com.example.readingroom"\n'
        '        versionCode 1\n        versionName "1.0"\n    }\n}\n')
    (app / 'src/main/AndroidManifest.xml').write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n\n'
        '    <application\n'
        '        android:allowBackup="true"\n'
        '        android:label="@string/app_name">\n'
        '    </application>\n</manifest>\n')
    return project


def test_harden_applies_what_the_capacitor_template_leaves_at_defaults(tmp_path):
    project = fake_android_project(generate(tmp_path))
    config_json = json.loads((project / 'capacitor.config.json').read_text())
    changes = mobile.harden_android(project, config_json)
    assert changes

    manifest_path = project / 'android/app/src/main/AndroidManifest.xml'
    manifest = manifest_path.read_text()
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert 'android:networkSecurityConfig="@xml/network_security_config"' in manifest
    assert 'android:allowBackup="false"' in manifest
    # Patched by string replacement, so it must still parse.
    ElementTree.parse(manifest_path)
    ElementTree.parse(project / 'android/app/src/main/res/xml/network_security_config.xml')
    assert 'versionName "1.0.0"' in (project / 'android/app/build.gradle').read_text()


def test_harden_is_idempotent(tmp_path):
    project = fake_android_project(generate(tmp_path))
    config_json = json.loads((project / 'capacitor.config.json').read_text())
    mobile.harden_android(project, config_json)
    assert mobile.harden_android(project, config_json) == []


def test_check_catches_hardening_lost_to_a_cap_add(tmp_path, capsys):
    """`npx cap add android` rewrites the native project. If nobody re-hardens, the
    build would ship with cleartext allowed and the wrong version."""
    project = fake_android_project(generate(tmp_path))
    # Icons are checked separately; this case is about hardening lost to a cap add.
    args = mobile.argparse.Namespace(output=str(project), require_icons=False)
    assert mobile.do_check(args) == 1
    errors = capsys.readouterr().err
    assert 'cleartext' in errors
    assert 'allowBackup' in errors
    assert 'versionName' in errors
    assert 'network_security_config.xml' in errors

    mobile.harden_android(project, json.loads((project / 'capacitor.config.json').read_text()))
    assert mobile.do_check(args) == 0


def test_init_refuses_to_clobber_an_existing_project(tmp_path):
    generate(tmp_path)
    with pytest.raises(mobile.InvalidInput):
        generate(tmp_path)
    generate(tmp_path, force=True)


def test_store_checklist_names_the_guidelines_that_sink_submissions(tmp_path):
    checklist = (generate(tmp_path) / 'store' / 'STORE-CHECKLIST.md').read_text()
    assert '4.2.2' in checklist, 'thin-wrapper rejection is the main App Store risk'
    assert 'In-App Purchase' in checklist, 'Stripe Checkout conflicts with guideline 3.1.1'
    assert 'com.example.readingroom' in checklist
