import pytest

from app import files, github


def state(head='parent', entries=None):
    return {'head': head, 'branch': 'main', 'tree': 'base-tree', 'entries': entries or {}}


def test_review_reports_diff_and_preserves_remote_only_files(tmp_path, monkeypatch):
    files.write(tmp_path, 'backend/app/main.py', 'print(2)\n')
    baseline = {'head': 'parent', 'branch': 'main',
                'files': {'backend/app/main.py': 'print(1)\n'}}
    monkeypatch.setattr(github, 'remote_state', lambda repo: state(entries={
        'backend/app/main.py': {'sha': github.blob_sha('print(1)\n')},
        'remote-notes.md': {'sha': 'remote-sha'},
    }))

    review = github.review('me/app', tmp_path, baseline)

    assert review['conflicts'] == []
    assert review['preserved_remote_files'] == 1
    assert review['changes'][0]['change'] == 'modified'
    assert '-print(1)' in review['changes'][0]['diff']
    assert '+print(2)' in review['changes'][0]['diff']


def test_review_detects_remote_divergence_and_unmanaged_collision(tmp_path, monkeypatch):
    files.write(tmp_path, 'backend/app/main.py', 'local')
    monkeypatch.setattr(github, 'remote_state', lambda repo: state('remote-new', {
        'backend/app/main.py': {'sha': github.blob_sha('remote')},
    }))

    review = github.review('me/app', tmp_path, {'head': 'old', 'branch': 'main', 'files': {}})

    assert any('changed since the last save' in item for item in review['conflicts'])
    assert any('unmanaged remote file' in item for item in review['conflicts'])


def test_reviewed_commit_never_force_pushes_and_preserves_unmanaged_files(tmp_path, monkeypatch):
    files.write(tmp_path, 'backend/app/main.py', 'print(42)')
    (tmp_path / '.env').write_text('secret=hidden')
    digest = files.digest(tmp_path)
    monkeypatch.setattr(github, 'remote_state', lambda repo: state(entries={
        'remote-only.md': {'sha': 'leave-this-tree-entry-alone'},
    }))
    called = []

    def api(path, method='GET', payload=None):
        called.append((path, method, payload))
        if path.endswith('/trees'):
            return {'sha': 'tree'}
        if path.endswith('/commits'):
            return {'sha': 'commit'}
        return {}

    monkeypatch.setattr(github, 'api', api)
    result = github.save('me/app', tmp_path, 'Save',
                         {'head': 'parent', 'branch': 'main', 'files': {}}, 'parent', digest)

    assert result['url'] == 'https://github.com/me/app/commit/commit'
    tree = next(payload for path, method, payload in called if path.endswith('/trees'))
    assert tree['base_tree'] == 'base-tree'
    assert [entry['path'] for entry in tree['tree']] == ['backend/app/main.py']
    assert called[-1][2]['force'] is False


def test_save_blocks_local_or_remote_change_after_review(tmp_path, monkeypatch):
    files.write(tmp_path, 'backend/app/main.py', 'reviewed')
    digest = files.digest(tmp_path)
    baseline = {'head': 'parent', 'branch': 'main', 'files': {}}
    files.write(tmp_path, 'backend/app/main.py', 'changed after review')
    monkeypatch.setattr(github, 'remote_state', lambda repo: pytest.fail('Local digest must fail first'))
    with pytest.raises(github.Conflict, match='Local source changed'):
        github.save('me/app', tmp_path, 'Save', baseline, 'parent', digest)

    digest = files.digest(tmp_path)
    monkeypatch.setattr(github, 'remote_state', lambda repo: state('remote-change'))
    with pytest.raises(github.Conflict, match='GitHub changed'):
        github.save('me/app', tmp_path, 'Save', baseline, 'parent', digest)


def test_secret_export_fails_before_github_access(tmp_path, monkeypatch):
    path = tmp_path / 'backend/app/main.py'
    path.parent.mkdir(parents=True)
    path.write_text('token = "github_pat_' + 'x' * 40 + '"')
    monkeypatch.setattr(github, 'remote_state', lambda *a, **kw: pytest.fail('Network must not be called'))
    with pytest.raises(ValueError, match='secret'):
        github.save('me/app', tmp_path, 'Save', {}, 'head', '0' * 64)


def test_public_repository_is_rejected(monkeypatch):
    monkeypatch.setattr(github, 'api', lambda *a, **kw: {'private': False})
    with pytest.raises(ValueError, match='private'):
        github.remote_state('me/app')
