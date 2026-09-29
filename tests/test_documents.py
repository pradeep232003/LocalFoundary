import zipfile

from app import config, documents


def test_local_index_searches_text_and_docx_with_citations(tmp_path, monkeypatch):
    source = tmp_path / 'documents'
    source.mkdir()
    (source / 'project-notes.md').write_text('Project Aurora uses a green deployment checklist and weekly review.')
    with zipfile.ZipFile(source / 'brief.docx', 'w') as archive:
        archive.writestr('word/document.xml',
            '<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>Aurora launch owner is Casey.</w:t></w:r></w:p></w:body></w:document>')
    outside = tmp_path / 'outside.txt'
    outside.write_text('secret external document')
    (source / 'escape.txt').symlink_to(outside)
    monkeypatch.setattr(config, 'DOCUMENTS', source)
    monkeypatch.setattr(config, 'DATA', tmp_path)

    status = documents.rebuild()
    results = documents.query('Aurora', 10)

    assert status['indexed_files'] == 2
    assert {result['path'] for result in results} == {'brief.docx', 'project-notes.md'}
    assert all('#chunk-' in result['citation'] for result in results)
    assert 'Casey' in documents.read('brief.docx', 1)
    assert all(result['path'] != 'escape.txt' for result in results)


def test_document_paths_cannot_escape_managed_folder(tmp_path, monkeypatch):
    source = tmp_path / 'documents'
    source.mkdir()
    monkeypatch.setattr(config, 'DOCUMENTS', source)
    try:
        documents.relative('../private.txt')
    except ValueError as exc:
        assert 'escapes' in str(exc)
    else:
        raise AssertionError('Path traversal must be rejected.')
