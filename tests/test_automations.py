import pytest

from app import automations, config


def test_file_plan_requires_preview_then_apply_and_undo(client, monkeypatch, tmp_path):
    project_id = client.post('/api/projects', json={'name': 'File agent'}).json()['id']
    root = tmp_path / 'managed-files'
    root.mkdir()
    (root / 'draft.txt').write_text('content is never read by the planning agent')
    monkeypatch.setattr(config, 'AUTOMATION_FILES', root)

    plan = automations.create_plan(project_id, 'Move drafts', [
        {'op': 'mkdir', 'source': '', 'destination': 'Writing'},
        {'op': 'move', 'source': 'draft.txt', 'destination': 'Writing/draft.txt'},
    ])
    assert plan['status'] == 'planned'
    assert (root / 'draft.txt').exists()

    applied = automations.apply(plan['id'], project_id)
    assert applied['status'] == 'applied'
    assert (root / 'Writing/draft.txt').read_text().startswith('content')

    undone = automations.undo(plan['id'], project_id)
    assert undone['status'] == 'undone'
    assert (root / 'draft.txt').exists()
    assert not (root / 'Writing').exists()


def test_file_plan_blocks_collision_and_changed_workspace(client, monkeypatch, tmp_path):
    project_id = client.post('/api/projects', json={'name': 'File safety'}).json()['id']
    root = tmp_path / 'managed-files'
    root.mkdir()
    (root / 'a.txt').write_text('a')
    (root / 'b.txt').write_text('b')
    monkeypatch.setattr(config, 'AUTOMATION_FILES', root)
    with pytest.raises(ValueError, match='already exists'):
        automations.create_plan(project_id, 'collision', [
            {'op': 'move', 'source': 'a.txt', 'destination': 'b.txt'}])

    plan = automations.create_plan(project_id, 'trash a', [
        {'op': 'trash', 'source': 'a.txt', 'destination': ''}])
    (root / 'b.txt').write_text('changed after preview')
    with pytest.raises(ValueError, match='changed after the preview'):
        automations.apply(plan['id'], project_id)
    assert (root / 'a.txt').exists()


def test_trash_is_recoverable(client, monkeypatch, tmp_path):
    project_id = client.post('/api/projects', json={'name': 'Trash safety'}).json()['id']
    root = tmp_path / 'managed-files'
    root.mkdir()
    (root / 'old.txt').write_text('recover me')
    monkeypatch.setattr(config, 'AUTOMATION_FILES', root)
    plan = automations.create_plan(project_id, 'remove old file', [
        {'op': 'trash', 'source': 'old.txt', 'destination': ''}])
    automations.apply(plan['id'], project_id)
    assert not (root / 'old.txt').exists()
    assert (root / '.foundry-trash' / plan['id'] / 'old.txt').exists()
    automations.undo(plan['id'], project_id)
    assert (root / 'old.txt').read_text() == 'recover me'
