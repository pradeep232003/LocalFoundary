"""Reviewable GitHub sync. Unmanaged remote files are preserved; divergence blocks writes."""
import difflib
import hashlib
import json
import re
from urllib.parse import quote

from . import files
from .process import run


class Conflict(ValueError):
    pass


def api(endpoint, method='GET', payload=None):
    args = ['gh', 'api', '--method', method, endpoint]
    if payload is not None:
        args += ['--input', '-']
    return json.loads(run(args, timeout=90, input_text=json.dumps(payload) if payload is not None else None,
                          output_limit=2_000_000))


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', name):
        raise ValueError('Use a repository name containing letters, numbers, dots, underscores, or hyphens.')
    return name


def create_private(name):
    return api('user/repos', 'POST', {'name': validate_name(name), 'private': True, 'auto_init': True,
                                    'description': 'App built locally with Local Foundry'})['full_name']


def blob_sha(content):
    body = content.encode('utf-8')
    return hashlib.sha1(f'blob {len(body)}\0'.encode() + body).hexdigest()


def remote_state(repo):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid repository.')
    info = api('repos/' + repo)
    if not info.get('private'):
        raise ValueError('This project is configured to save to a private repository.')
    branch = info['default_branch']
    head = api(f'repos/{repo}/git/ref/heads/{quote(branch, safe="")}')['object']['sha']
    commit = api(f'repos/{repo}/git/commits/{head}')
    tree_sha = commit['tree']['sha']
    tree = api(f'repos/{repo}/git/trees/{tree_sha}?recursive=1')
    if tree.get('truncated'):
        raise Conflict('The remote file tree is too large to review safely.')
    entries = {e['path']: e for e in tree['tree'] if e['type'] != 'tree'}
    return {'head': head, 'branch': branch, 'tree': tree_sha, 'entries': entries}


def review(repo, source, baseline, *, initial=False):
    content = files.export(source)
    local_digest = files.digest(source)
    baseline = baseline or {}
    prior = baseline.get('files', {})
    state = remote_state(repo) if repo else None
    problems = []
    if state:
        if not initial and not baseline.get('head'):
            problems.append('This older project has no sync baseline. Use a new private repository or reconcile it locally first.')
        elif baseline.get('head') and (state['head'] != baseline['head'] or state['branch'] != baseline.get('branch')):
            problems.append('GitHub has changed since the last save. Pull and reconcile those edits before saving again.')
        for path in content:
            remote = state['entries'].get(path)
            if remote and path not in prior and remote['sha'] != blob_sha(content[path]):
                problems.append(f'{path}: an unmanaged remote file would be overwritten.')
    changes = []
    for path in sorted(set(content) | set(prior)):
        before, after = prior.get(path), content.get(path)
        if before == after:
            continue
        change = 'added' if before is None else 'deleted' if after is None else 'modified'
        diff = ''.join(difflib.unified_diff((before or '').splitlines(True), (after or '').splitlines(True),
                                           fromfile='before/' + path, tofile='after/' + path))
        changes.append({'path': path, 'change': change, 'diff': diff[:16000], 'truncated': len(diff) > 16000})
    return {'repo': repo, 'head': state['head'] if state else None,
            'branch': state['branch'] if state else None, 'source_digest': local_digest,
            'changes': changes, 'conflicts': problems,
            'preserved_remote_files': len(set(state['entries']) - set(prior) - set(content)) if state else 0}


def save(repo, source, message, baseline, expected_head, expected_digest):
    content = files.export(source)
    if files.digest(source) != expected_digest:
        raise Conflict('Local source changed after review. Review the changes again.')
    state = remote_state(repo)
    if state['head'] != expected_head or state['head'] != baseline.get('head'):
        raise Conflict('GitHub changed after review. No files were overwritten.')
    if state['branch'] != baseline.get('branch'):
        raise Conflict('The GitHub default branch changed. Review the repository again.')
    prior = baseline.get('files', {})
    entries = []
    for path, value in sorted(content.items()):
        remote = state['entries'].get(path)
        if remote and path not in prior and remote['sha'] != blob_sha(value):
            raise Conflict(f'Unmanaged remote file conflicts with {path}. No files were overwritten.')
        if not remote or remote['sha'] != blob_sha(value):
            entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'content': value})
    for path in sorted(set(prior) - set(content)):
        if path in state['entries']:
            entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'sha': None})
    head = state['head']
    if entries:
        tree = api(f'repos/{repo}/git/trees', 'POST', {'base_tree': state['tree'], 'tree': entries})
        commit = api(f'repos/{repo}/git/commits', 'POST', {'message': message, 'tree': tree['sha'], 'parents': [head]})
        api(f'repos/{repo}/git/refs/heads/{quote(state["branch"], safe="")}', 'PATCH',
            {'sha': commit['sha'], 'force': False})
        head = commit['sha']
    return {'url': f'https://github.com/{repo}/commit/{head}',
            'baseline': {'head': head, 'branch': state['branch'], 'files': content}}
