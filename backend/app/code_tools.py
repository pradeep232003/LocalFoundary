"""Hash-guarded precise edits and bounded symbol/import/source search."""
import ast
import difflib
import hashlib
import re
from pathlib import PurePosixPath
from . import files


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def inspect(root, path):
    content = files.read(root, path)
    return {'path': path, 'sha256': sha(content), 'lines': len(content.splitlines()), 'content': content}


def patch(root, path, expected_sha256, edits):
    original = files.read(root, path)
    if expected_sha256 != sha(original):
        raise ValueError('File changed or was not read completely. Inspect it again before patching.')
    if not isinstance(edits, list) or not 1 <= len(edits) <= 20:
        raise ValueError('Provide 1–20 exact, unambiguous text replacements.')
    updated = original
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'old', 'new'} or any(not isinstance(edit[k], str) for k in edit):
            raise ValueError('Each replacement needs old and new text.')
        if not edit['old'] or updated.count(edit['old']) != 1:
            raise ValueError('Each old-text block must match exactly once. Include more surrounding context.')
        updated = updated.replace(edit['old'], edit['new'], 1)
    if original == updated:
        raise ValueError('The patch makes no change.')
    # All replacements are checked before the atomic write; a bad final replacement changes nothing.
    result = files.write(root, path, updated)
    diff = ''.join(difflib.unified_diff(original.splitlines(True), updated.splitlines(True), fromfile=path, tofile=path))
    return {'message': result, 'sha256': sha(updated), 'diff': diff[:18000], 'diff_truncated': len(diff) > 18000}


def index(root):
    result = []
    for path in files.list_files(root):
        if PurePosixPath(path).suffix not in {'.py', '.js', '.jsx', '.ts', '.tsx'}:
            continue
        source = files.read(root, path)
        symbols, imports = [], []
        if path.endswith('.py'):
            try:
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        symbols.append({'name': node.name, 'line': node.lineno, 'kind': type(node).__name__})
                    elif isinstance(node, ast.Import):
                        imports.extend(item.name for item in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append('.' * node.level + (node.module or ''))
            except SyntaxError:
                pass
        else:
            for line, value in enumerate(source.splitlines(), 1):
                match = re.search(r'\b(?:function|class|const|let)\s+([A-Za-z_$][\w$]*)', value)
                if match:
                    symbols.append({'name': match[1], 'line': line, 'kind': 'javascript declaration'})
                imports.extend(re.findall(r'''(?:from\s*|import\s*\(|require\s*\()?["']([./@\w-]+(?:[./\w-]*))["']''', value) if value.lstrip().startswith(('import ', 'export ')) else [])
        result.append({'path': path, 'sha256': sha(source), 'symbols': symbols[:80], 'imports': sorted(set(imports))[:60]})
    return result


def search(root, query):
    if not isinstance(query, str) or not 2 <= len(query) <= 120 or files.SECRET.search(query):
        raise ValueError('Search for 2–120 characters without secrets.')
    matches = []
    for path in files.list_files(root):
        for number, line in enumerate(files.read(root, path).splitlines(), 1):
            if query.casefold() in line.casefold():
                matches.append({'path': path, 'line': number, 'text': line[:300]})
                if len(matches) == 60:
                    return {'matches': matches, 'truncated': True}
    return {'matches': matches, 'truncated': False}
