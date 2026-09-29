"""Bugs reproduced while reviewing the uploaded v0.6.3 release."""
from contextlib import contextmanager
import importlib.util
import json
import plistlib

import psycopg
import pytest

from app import config, db, documents


def mobile_module():
    spec = importlib.util.spec_from_file_location('mobile_review', config.ROOT / 'scripts/mobile.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('batch', [False, True])
def test_uncertain_database_write_is_never_replayed(monkeypatch, batch):
    committed = []
    class Connection:
        def execute(self, sql, params):
            committed.append(sql)
            if not batch:
                raise psycopg.OperationalError('connection lost after server committed')
        @contextmanager
        def transaction(self):
            yield
            raise psycopg.OperationalError('commit acknowledgement lost')
    @contextmanager
    def connection():
        yield Connection()
    monkeypatch.setattr(db, 'connection', connection)
    with pytest.raises(psycopg.OperationalError):
        if batch:
            db.batch([('INSERT event', ())])
        else:
            db.query('INSERT event')
    assert committed == ['INSERT event'], 'An uncertain write must surface once, not run again.'


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be'])
def test_docx_dtd_rejected_independent_of_xml_encoding(encoding):
    declaration = 'UTF-8' if encoding == 'utf-8' else 'UTF-16'
    xml = f'<?xml version="1.0" encoding="{declaration}"?><!DOCTYPE a [<!ENTITY x "expanded">]><a>&x;</a>'
    with pytest.raises(ValueError, match='DTD'):
        documents.safe_xml(xml.encode(encoding))


def test_valid_utf16_docx_xml_still_parses():
    xml = '<?xml version="1.0" encoding="UTF-16"?><a>Normal document</a>'
    assert documents.safe_xml(xml.encode('utf-16')).text == 'Normal document'


@pytest.mark.parametrize('value', ['com.example.reading_room', 'com.new.app'])
def test_mobile_id_satisfies_both_native_platforms(value):
    module = mobile_module()
    with pytest.raises(module.InvalidInput):
        module.validate_app_id(value)


def test_offline_app_name_is_text_not_markup():
    module = mobile_module()
    result = module.render_offline_page('<img src=x onerror=alert(1)>', 'https://app.example.com')
    assert '<img src=x' not in result
    assert '&lt;img src=x' in result


def project(module, tmp_path):
    module.do_init(module.argparse.Namespace(origin='https://app.example.com', name='Review',
        app_id='com.example.review', version='1.2.3', output=str(tmp_path), force=True, debuggable=False))
    # These cases are about native hardening, not store readiness. do_check reports a
    # missing icon set as a failure by default, because shipping Capacitor's
    # placeholder logo is a guaranteed rejection; that is covered in
    # test_mobile_assets.py and would only be noise here.
    return module.argparse.Namespace(output=str(tmp_path), require_icons=False)


def test_checker_rejects_unsafe_android_network_xml(tmp_path):
    module = mobile_module()
    args = project(module, tmp_path)
    folder = tmp_path / 'android/app/src/main'
    folder.mkdir(parents=True)
    (folder / 'AndroidManifest.xml').write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application android:usesCleartextTraffic="true"/></manifest>')
    (tmp_path / 'android/app/build.gradle').write_text('versionName "1.0"')
    configuration = json.loads((tmp_path / 'capacitor.config.json').read_text())
    module.harden_android(tmp_path, configuration)
    assert module.do_check(args) == 0
    path = folder / 'res/xml/network_security_config.xml'
    path.write_text(path.read_text().replace('cleartextTrafficPermitted="false"', 'cleartextTrafficPermitted="true"'))
    assert module.do_check(args) == 1
    module.harden_android(tmp_path, configuration)
    assert module.do_check(args) == 0


def test_ios_hardening_records_remote_and_fallback_domains(tmp_path):
    module = mobile_module()
    args = project(module, tmp_path)
    info = tmp_path / 'ios/App/App/Info.plist'
    info.parent.mkdir(parents=True)
    info.write_bytes(plistlib.dumps({'CFBundleVersion':'1'}))
    assert module.do_check(args) == 1
    configuration = json.loads((tmp_path / 'capacitor.config.json').read_text())
    assert configuration['server']['iosScheme'] == 'capacitor'
    module.harden_ios(tmp_path, configuration)
    assert module.do_check(args) == 0
    values = plistlib.loads(info.read_bytes())
    assert set(values['WKAppBoundDomains']) == {'app.example.com', 'localhost'}
    assert values['CFBundleShortVersionString'] == '1.2.3'
    assert values['CFBundleVersion'] == '1'


def test_generated_mobile_check_is_self_contained(tmp_path):
    module = mobile_module()
    project(module, tmp_path)
    assert (tmp_path / 'tools/mobile.py').is_file()
    package = json.loads((tmp_path / 'package.json').read_text())
    assert package['scripts']['check'] == 'python3 tools/mobile.py check --output .'
