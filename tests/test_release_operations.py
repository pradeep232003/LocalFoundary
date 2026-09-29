import importlib.util
import io
import json
import secrets
import sys
import pytest
from app import config, db, files, journeys, releases, sandbox
from test_accounts import accounts  # noqa: F401  (pytest fixture, used by name)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


crypto = module('backup_crypto', config.ROOT/'release-template/ops/crypto_stream.py')
operations = module('release_operations', config.ROOT/'release-template/ops.py')
monitor = module('external_monitor', config.ROOT/'release-template/ops/external_monitor.py')
contracts = module('protected_contracts', config.ROOT/'protected/security_cases.py')


def test_encrypted_dump_round_trip_authenticates_before_output():
    key = secrets.token_bytes(32)
    plain = b'PGDMP' + secrets.token_bytes(2_100_000)
    target = io.BytesIO()
    crypto.transform('encrypt', io.BytesIO(key+plain), target)
    encrypted = target.getvalue()
    restored = io.BytesIO()
    crypto.transform('decrypt', io.BytesIO(key+encrypted), restored)
    assert restored.getvalue() == plain
    assert plain[:50] not in encrypted
    for wrong in (encrypted[:-1], encrypted[:40]+bytes([encrypted[40]^1])+encrypted[41:], encrypted[:6]+bytes([encrypted[6]^1])+encrypted[7:]):
        restored = io.BytesIO()
        with pytest.raises(Exception):
            crypto.transform('decrypt', io.BytesIO(key+wrong), restored)
        assert restored.getvalue() == b''
    with pytest.raises(Exception):
        crypto.transform('decrypt', io.BytesIO(secrets.token_bytes(32)+encrypted), io.BytesIO())


def test_backup_limit_and_missing_key_do_not_silently_rotate(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, 'MAX_BYTES', 32)
    with pytest.raises(ValueError, match='limit'):
        crypto.transform('encrypt', io.BytesIO(b'x'*32+b'PGDMP'+b'x'*100), io.BytesIO())
    monkeypatch.setattr(operations, 'STATE', tmp_path)
    with pytest.raises(ValueError, match='missing'):
        operations.key_bytes(create=False)
    assert not (tmp_path/'backup.key').exists()
    key = operations.key_bytes()
    assert operations.key_bytes() == key
    assert (tmp_path/'backup.key').stat().st_mode & 0o077 == 0


def test_binary_process_pipeline_round_trip_and_failed_authentication(tmp_path):
    key = secrets.token_bytes(32)
    path = tmp_path/'backup.lfb'
    restored = tmp_path/'restored.dump'
    crypto_script = str(config.ROOT/'release-template/ops/crypto_stream.py')
    producer = [sys.executable, '-c', "import sys;sys.stdout.buffer.write(b'PGDMP'+b'abcd'*300000)"]
    with path.open('wb') as output:
        operations.pipeline(producer, [sys.executable, crypto_script, 'encrypt'], key, destination=output)
    consumer = [sys.executable, '-c', "import sys;open(sys.argv[1],'wb').write(sys.stdin.buffer.read())", str(restored)]
    with path.open('rb') as source:
        operations.pipeline([sys.executable, crypto_script, 'decrypt'], consumer, key, source=source)
    assert restored.read_bytes() == b'PGDMP'+b'abcd'*300000
    with path.open('rb') as source, pytest.raises(RuntimeError):
        operations.pipeline([sys.executable, crypto_script, 'decrypt'], consumer, secrets.token_bytes(32), source=source)
    assert restored.read_bytes() == b''


def test_database_migration_changes_block_image_rollback():
    old = {'migrations': {'001_initial.sql': 'a'*64}}
    assert operations.compatible(old, old['migrations'])
    assert not operations.compatible(old, {'001_initial.sql': 'b'*64})
    assert not operations.compatible(old, {**old['migrations'], '002_new.sql':'c'*64})
    assert not operations.compatible(None, {})


def test_external_monitor_requires_three_failures_and_recovery():
    state = {}
    for _ in range(2):
        state, event = monitor.transition(state, False)
        assert event is None
    state, event = monitor.transition(state, False)
    assert event == 'down'
    state['alerted'] = True
    state, event = monitor.transition(state, False)
    assert event is None
    state, event = monitor.transition(state, True)
    assert event == 'recovered' and state['failures'] == 0
    with pytest.raises(ValueError):
        monitor.https('http://app.example.com')


def test_protected_contracts_exercise_actual_kit(accounts):
    client, database, _ = accounts
    contracts.exercise(client, database)


def test_protected_contract_detects_removed_authorization(accounts, monkeypatch):
    client, database, _ = accounts
    original = client.get
    monkeypatch.setattr(client, 'get', lambda path, *a, **kw: type('Response', (), {'status_code':200})() if path == '/api/notes' else original(path, *a, **kw))
    with pytest.raises(AssertionError, match='Anonymous protected read'):
        contracts.exercise(client, database)


def test_accounts_release_requires_current_trusted_contracts(client):
    pid = client.post('/api/projects', json={'name':'Accounts','profile':'accounts'}).json()['id']
    digest = files.digest(sandbox.source_dir(pid))
    report = {'status':'passed', 'source_digest':digest, 'gate_version':6, 'browser_checks':True, 'checks':[]}
    with pytest.raises(ValueError, match='security contracts'):
        releases.bundle(pid, report, digest)
    report['checks'] = [{'name':name, 'status':'passed'} for name in ('Protected security contracts', 'Authenticated user journeys')]
    assert releases.bundle(pid, report, digest).startswith(b'PK')


def test_journey_failure_cleans_only_its_disposable_stack(client, monkeypatch):
    pid = client.post('/api/projects', json={'name':'Journeys','profile':'accounts'}).json()['id']
    calls = []
    def fail(args, **kwargs):
        calls.append(args)
        if 'up' in args:
            raise RuntimeError('Cannot connect to the Docker daemon')
        return ''
    monkeypatch.setattr(journeys, 'run', fail)
    with pytest.raises(RuntimeError):
        journeys.check(pid)
    cleanups = [args for args in calls if 'down' in args]
    assert len(cleanups) == 1 and '--volumes' in cleanups[0]
    assert cleanups[0][cleanups[0].index('-p')+1].startswith('foundry-journey-')
    assert cleanups[0][cleanups[0].index('-p')+1] != 'foundry-'+pid
    assert not list(sandbox.project_dir(pid).glob('foundry-journey-*.json'))
