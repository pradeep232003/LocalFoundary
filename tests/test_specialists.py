import json
import threading

from app import config, providers, specialists, usage
from conftest import make_run


def limits():
    return usage.Limits(2.0, 180_000, 24_000, 2.5, 15.0)


def test_document_agent_replaces_an_uncited_direct_answer(client, monkeypatch):
    project_id = client.post('/api/projects', json={'name': 'Citation guard'}).json()['id']

    def answer(*args, **kwargs):
        return [], ['An answer that did not consult the index.'], [], {
            'input_tokens': 20, 'output_tokens': 8}, False

    monkeypatch.setattr(providers, 'ask', answer)
    final, _, plan = specialists.run(project_id, make_run(project_id), 'openai', 'What is documented?',
                                     threading.Event(), limits(), 'documents')

    assert 'citation-backed answer' in final
    assert plan is None


def test_file_agent_tool_result_contains_metadata_but_not_file_contents(client, monkeypatch, tmp_path):
    project_id = client.post('/api/projects', json={'name': 'Metadata boundary'}).json()['id']
    root = tmp_path / 'managed-files'
    root.mkdir()
    (root / 'private.txt').write_text('contents must never enter the model context')
    monkeypatch.setattr(config, 'AUTOMATION_FILES', root)
    seen = []

    def answer(provider, history, max_output_tokens=8000, on_retry=None, system=None, tools=None):
        seen.append(json.dumps(history))
        if len(seen) == 1:
            item = {'type': 'function_call', 'call_id': 'list-1',
                    'name': 'list_workspace_files', 'arguments': '{}'}
            return [item], [], [{'id': 'list-1', 'name': 'list_workspace_files',
                                 'arguments': '{}'}], {'input_tokens': 20, 'output_tokens': 8}, False
        return [], ['I inspected filenames only.'], [], {
            'input_tokens': 30, 'output_tokens': 9}, False

    monkeypatch.setattr(providers, 'ask', answer)
    final, _, plan = specialists.run(project_id, make_run(project_id, 'b' * 32), 'openai', 'Review these filenames.',
                                     threading.Event(), limits(), 'files')

    assert 'private.txt' in seen[1]
    assert 'contents must never enter' not in seen[1]
    assert final == 'I inspected filenames only.'
    assert plan is None
