import json
import pytest
from app import config, sandbox


def test_preview_configuration_has_no_host_credentials_or_privileged_mounts(tmp_path):
    spec = sandbox.compose_config(tmp_path, 'a' * 32)
    assert spec['networks']['app']['internal'] is True
    for name, service in spec['services'].items():
        assert service['user'] != '0:0'
        assert service['read_only']
        assert service['cap_drop'] == ['ALL']
        assert 'no-new-privileges:true' in service['security_opt']
        assert service['pids_limit'] <= 128
        assert service['mem_limit'] == '2g'
        for volume in service.get('volumes', []):
            if isinstance(volume, dict):
                assert volume['read_only']
                assert volume['source'].startswith(str(tmp_path) + '/')
    assert 'ports' not in spec['services']['db']
    assert 'ports' not in spec['services']['api']
    assert spec['services']['web']['ports'][0]['host_ip'] == '127.0.0.1'
    assert spec['services']['api']['image'].endswith(':2')
    assert any(volume.get('target') == '/app/migrations' for volume in spec['services']['api']['volumes'])
    encoded = json.dumps(spec)
    assert 'docker.sock' not in encoded and 'API_KEY' not in encoded and '/Users/' not in encoded


def test_model_commands_execute_only_inside_container(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(sandbox, 'command', lambda *args, **kwargs: seen.append((args, kwargs)) or 'ok')
    command = 'python -c "print(42)"; cat /etc/passwd'
    sandbox.execute('a' * 32, 'api', command)
    args, options = seen[0]
    assert args[1:4] == ('exec', '-T', 'api')
    assert args[-1] == command
    assert 'timeout' in args and '--kill-after=5' in args
    with pytest.raises(ValueError):
        sandbox.execute('a' * 32, 'db', 'DROP DATABASE app')


def test_untrusted_compose_is_never_used(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'PROJECTS', tmp_path)
    project = tmp_path / ('b' * 32); project.mkdir()
    (project / 'source').mkdir()
    (project / 'source/compose.json').write_text('{"privileged":true}')
    observed = []
    monkeypatch.setattr(sandbox, 'run', lambda argv, **kw: observed.append(argv) or '')
    sandbox.command('b' * 32, 'ps')
    argv = observed[0]
    assert argv[3] == str(project / 'runtime.json')
    assert json.loads((project / 'runtime.json').read_text())['services']['api']['cap_drop'] == ['ALL']


def test_api_check_uses_disposable_test_database(monkeypatch):
    calls = []
    monkeypatch.setattr(sandbox, 'prepare_test_database', lambda project_id: calls.append(('prepare', project_id)))
    monkeypatch.setattr(sandbox, 'test_command',
                        lambda project_id, *args: calls.append(('run', args)) or 'ok\n')

    output = sandbox.check('a' * 32, 'api')

    assert calls[0] == ('prepare', 'a' * 32)
    assert calls[1][1] == ('python', '/opt/foundry/runtime.py', 'migrate')
    assert calls[2][1][-2:] == ('no:cacheprovider', '/app/tests')
    assert output == 'ok\nok\n'
