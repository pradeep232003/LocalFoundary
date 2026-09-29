import threading
import pytest
from app import agent, builder, code_tools, continuity_archive, db, features, files, memory, providers, sandbox, usage
from conftest import make_run, wait_run


def new(client):
    return client.post('/api/projects', json={'name': 'Continuity'}).json()['id']


def test_context_revision_and_agent_notes_survive_user_edits(client):
    pid = new(client)
    assert memory.save(pid, {'requirements': 'Private journal'}, 0)['revision'] == 1
    memory.remember(pid, 'Notes use PostgreSQL.')
    with pytest.raises(ValueError, match='changed'):
        memory.save(pid, {'requirements': 'Stale editor'}, 1)
    data = memory.save(pid, {'requirements': 'A personal journal'}, 2)
    assert data['agent_notes'][0]['text'] == 'Notes use PostgreSQL.'
    assert 'A personal journal' in memory.context(pid)


def test_patch_staleness_atomicity_and_boundaries(client):
    pid = new(client)
    root = sandbox.source_dir(pid)
    path = 'backend/app/main.py'
    original = files.read(root, path)
    digest = code_tools.sha(original)
    with pytest.raises(ValueError, match='changed'):
        code_tools.patch(root, path, '0'*64, [{'old': original, 'new': 'x'}])
    with pytest.raises(ValueError, match='exactly once'):
        code_tools.patch(root, path, digest, [{'old': original, 'new': 'x'}, {'old': 'absent', 'new': ''}])
    assert files.read(root, path) == original
    result = code_tools.patch(root, path, digest, [{'old': original, 'new': original + '\n# precise change\n'}])
    assert '+# precise change' in result['diff']
    with pytest.raises(ValueError):
        code_tools.patch(root, '../runtime.json', digest, [])
    assert code_tools.search(root, 'precise change')['matches'][0]['path'] == path
    assert any(row['symbols'] for row in code_tools.index(root))


def test_resume_preserves_budget_and_skips_completed_milestone(client, monkeypatch):
    pid = new(client)
    items = [{'title': f'Feature {n}', 'prompt': 'Implement a small feature', 'acceptance': 'Checks pass'} for n in range(2)]
    plan = features.create(pid, 'Two features', items)
    limits = usage.Limits(0, 100000, 10000, 0, 0)
    count = []
    def fake_build(*args, **kwargs):
        session = kwargs['session']
        count.append(session['restrict_commands'])
        session['meter'].record('local', {'input_tokens': 100, 'output_tokens': 50})
        session['checkpoint']('tool_started', tool='write_file')
        if len(count) == 2:
            raise InterruptedError('Simulated process interruption')
        return 'Implemented and checked', session['meter'].data()
    monkeypatch.setattr(builder, 'run', fake_build)
    options = {'max_repairs': 0, 'browser_checks': True, 'share_screenshots': False}
    args = (pid, plan['id'], make_run(pid), threading.Event(), 'local', 'test-model', limits, options, files.digest(sandbox.source_dir(pid)))
    with pytest.raises(InterruptedError):
        features.execute(*args, False, lambda *a: None)
    saved = features.get(pid, plan['id'])
    assert [i['status'] for i in saved['milestones']] == ['completed', 'needs_review']
    with pytest.raises(ValueError, match='Review'):
        features.execute(*args, False, lambda *a: None)
    features.execute(*args, True, lambda *a: None)
    saved = features.get(pid, plan['id'])
    assert saved['status'] == 'completed' and saved['usage']['input_tokens'] == 300
    assert count == [False, False, True]


def test_lost_response_reserved_once_and_archive_preserves_it(client):
    pid = new(client)
    memory.save(pid, {'architecture': 'React and FastAPI'}, 0)
    plan = features.create(pid, 'Recover', [{'title': 'One', 'prompt': 'Build', 'acceptance': 'Works'}])
    plan['checkpoint'] = {'reservation': {'input_tokens': 500, 'output_tokens': 256, 'estimated_usd': .2}}
    features.persist(plan)
    restored = new(client)
    db.batch(continuity_archive.statements(restored, continuity_archive.export(pid)))
    data = features.listing(restored)[0]
    assert data['status'] == 'needs_review'
    assert memory.get(restored)['body']['architecture'] == 'React and FastAPI'
    meter = features.meter_from(data, usage.Limits())
    assert meter.requests == 1 and meter.estimated_usd == .2
    assert features.meter_from(features.get(restored, data['id']), usage.Limits()).requests == 1


def test_plan_proposal_pauses_remaining_tools(client, monkeypatch):
    pid = new(client)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(providers, 'ask', lambda *a, **kw: ([], [], [
        {'id': 'one', 'name': 'plan_features', 'arguments': {'title': 'Plan', 'milestones': [{'title': 'One', 'prompt': 'Build', 'acceptance': 'Works'}]}},
        {'id': 'two', 'name': 'write_file', 'arguments': {'path': 'frontend/src/blocked.js', 'content': 'bad'}}],
        {'input_tokens': 100, 'output_tokens': 50}, False))
    response = wait_run(client, client.post(f'/api/projects/{pid}/build', json={'provider': 'openai', 'prompt': 'Plan this app'}))
    assert response['status'] == 'awaiting_plan'
    assert len(features.listing(pid)) == 1
    assert not (sandbox.source_dir(pid) / 'frontend/src/blocked.js').exists()


def test_unknown_usage_keeps_checkpoint_reservation(client, monkeypatch):
    pid = new(client)
    db.message(pid, 'user', 'Build something')
    checkpoints = []
    monkeypatch.setattr(providers, 'ask', lambda *a, **kw: ([], [], [], {}, False))
    with pytest.raises(usage.BudgetExceeded):
        agent.build(pid, make_run(pid), 'local', threading.Event(), usage.Limits(0, 100000, 10000, 0, 0),
                    session={'checkpoint': lambda phase, **extra: checkpoints.append((phase, extra))})
    assert len(checkpoints) == 1 and 'reservation' in checkpoints[0][1]
