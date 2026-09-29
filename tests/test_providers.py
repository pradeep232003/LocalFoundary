import json
import httpx
import pytest
from app import providers


@pytest.mark.parametrize('provider', ['anthropic', 'openai'])
def test_real_wire_format_and_tool_result_round_trip(monkeypatch, provider):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    captured = []
    original = httpx.Client
    def handler(request):
        captured.append((request, json.loads(request.content)))
        if provider == 'openai':
            return httpx.Response(200, json={'status': 'completed', 'output': [
                {'type': 'reasoning', 'encrypted_content': 'opaque', 'summary': []},
                {'type': 'function_call', 'id': 'fc_1', 'call_id': 'call_1', 'name': 'list_files', 'arguments': '{}'}],
                'usage': {'input_tokens': 20, 'output_tokens': 10}})
        return httpx.Response(200, json={'stop_reason': 'tool_use', 'content': [
            {'type': 'tool_use', 'id': 'call_1', 'name': 'list_files', 'input': {}}],
            'usage': {'input_tokens': 20, 'output_tokens': 10}})
    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    history = [{'role': 'user', 'content': 'Build an app'}]
    items, texts, calls, usage, truncated = providers.ask(provider, history, max_output_tokens=4321)
    assert calls[0]['name'] == 'list_files' and not truncated
    providers.append_turn(provider, history, items, [{'id': 'call_1', 'text': 'main.py', 'error': False}])
    request, payload = captured[0]
    if provider == 'openai':
        assert payload['max_output_tokens'] == 4321
        assert payload['store'] is False
        assert payload['include'] == ['reasoning.encrypted_content']
        assert history[-1]['type'] == 'function_call_output'
        assert history[-3]['encrypted_content'] == 'opaque'
        assert all(tool['strict'] for tool in payload['tools'])
    else:
        assert payload['max_tokens'] == 4321
        assert request.headers['anthropic-version'] == '2023-06-01'
        assert history[-1]['content'][0]['type'] == 'tool_result'
        assert payload['tools'][0]['input_schema']['type'] == 'object'


def test_provider_errors_do_not_echo_submitted_content(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'key-for-test')
    original = httpx.Client
    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: original(
        transport=httpx.MockTransport(lambda r: httpx.Response(401, text='sensitive prompt leaked here')), **kwargs))
    with pytest.raises(RuntimeError) as exc:
        providers.ask('openai', [{'role': 'user', 'content': 'private'}])
    assert '401' in str(exc.value) and 'sensitive' not in str(exc.value)


def test_retryable_response_honors_bounded_retry_after(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'key-for-test')
    original = httpx.Client
    attempts = []
    responses = iter([
        httpx.Response(429, headers={'retry-after': '90'}),
        httpx.Response(200, json={'status': 'completed', 'output': [],
                                  'usage': {'input_tokens': 4, 'output_tokens': 2}}),
    ])
    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: original(
        transport=httpx.MockTransport(lambda request: next(responses)), **kwargs))
    monkeypatch.setattr(providers.time, 'sleep', lambda seconds: attempts.append(seconds))
    retries = []

    providers.ask('openai', [{'role': 'user', 'content': 'retry'}],
                  on_retry=lambda attempt, delay, reason: retries.append((attempt, delay, reason)))

    assert attempts == [15.0]
    assert retries == [(1, 15.0, 'HTTP 429')]


def test_local_openai_compatible_provider_stays_on_loopback(monkeypatch):
    monkeypatch.setitem(providers.MODELS, 'local', 'local-test-model')
    monkeypatch.setattr(providers.config, 'LOCAL_API_BASE', 'http://127.0.0.1:11434/v1')
    monkeypatch.setattr(providers.config, 'OFFLINE_ONLY', True)
    captured = []
    original = httpx.Client

    def handler(request):
        captured.append((request, json.loads(request.content)))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'tool_calls', 'message': {
            'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'local-1', 'type': 'function',
                'function': {'name': 'list_files', 'arguments': '{}'}}]}}],
            'usage': {'prompt_tokens': 40, 'completion_tokens': 8}})

    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs))
    items, texts, calls, usage_data, truncated = providers.ask(
        'local', [{'role': 'user', 'content': 'Inspect files'}], max_output_tokens=500)

    request, payload = captured[0]
    assert str(request.url).startswith('http://127.0.0.1:11434/v1/chat/completions')
    assert calls[0]['name'] == 'list_files'
    assert usage_data == {'input_tokens': 40, 'output_tokens': 8}
    assert payload['messages'][0]['role'] == 'system'
    assert not truncated


def test_local_provider_does_not_invent_missing_usage(monkeypatch):
    monkeypatch.setitem(providers.MODELS, 'local', 'local-test-model')
    monkeypatch.setattr(providers.config, 'LOCAL_API_BASE', 'http://127.0.0.1:11434/v1')
    original = httpx.Client
    monkeypatch.setattr(providers.httpx, 'Client', lambda **kwargs: original(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
            'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'done'}}]})),
        **kwargs))

    *_, usage_data, truncated = providers.ask('local', [{'role': 'user', 'content': 'hello'}])

    assert usage_data == {}
    assert not truncated


def test_offline_mode_blocks_remote_provider_and_non_loopback_local_url(monkeypatch):
    monkeypatch.setattr(providers.config, 'OFFLINE_ONLY', True)
    monkeypatch.setenv('OPENAI_API_KEY', 'configured-but-blocked')
    with pytest.raises(ValueError, match='Offline-only'):
        providers.key_for('openai')
    monkeypatch.setitem(providers.MODELS, 'local', 'local-model')
    monkeypatch.setattr(providers.config, 'LOCAL_API_BASE', 'https://example.com/v1')
    with pytest.raises(ValueError, match='loopback'):
        providers.key_for('local')
    monkeypatch.setattr(providers.config, 'LOCAL_API_BASE', 'http://127.0.0.1:11434/v1?target=remote')
    with pytest.raises(ValueError, match='loopback'):
        providers.key_for('local')
