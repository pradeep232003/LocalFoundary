"""Local, citation-first document index. Nothing leaves the managed documents folder."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader

from . import config, db
from .process import run

MAX_FILE = 20_000_000
MAX_TEXT = 2_000_000
MAX_FILES = 5_000
EXTENSIONS = {'.txt', '.md', '.rst', '.csv', '.json', '.py', '.js', '.jsx', '.ts', '.tsx',
              '.css', '.html', '.sql', '.log', '.pdf', '.docx', '.png', '.jpg', '.jpeg', '.tiff'}
lock = threading.Lock()


def database_path():
    return config.DATA / 'document-index.sqlite'


def relative(path):
    root = config.DOCUMENTS.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or target.is_symlink():
        raise ValueError('Document path escapes the managed documents folder.')
    return target


def source_files():
    result = []
    for directory, dirs, names in os.walk(config.DOCUMENTS, followlinks=False):
        dirs[:] = [name for name in dirs if not name.startswith('.') and not (Path(directory) / name).is_symlink()]
        for name in names:
            path = Path(directory) / name
            if name.startswith('.') or path.is_symlink() or path.suffix.lower() not in EXTENSIONS:
                continue
            if path.stat().st_size > MAX_FILE:
                continue
            result.append(path)
            if len(result) > MAX_FILES:
                raise ValueError('The documents folder exceeds 5,000 supported files.')
    return sorted(result)


def ocr_image(path):
    executable = shutil.which('tesseract')
    if not executable:
        return ''
    return run([executable, str(path), 'stdout', '-l', 'eng'], timeout=120, output_limit=MAX_TEXT)


def pdf_text(path):
    reader = PdfReader(str(path), strict=False)
    text = '\n\n'.join((page.extract_text() or '') for page in reader.pages[:200])
    if len(text.strip()) >= 80 or not shutil.which('pdftoppm') or not shutil.which('tesseract'):
        return text
    temporary = Path(tempfile.mkdtemp(prefix='foundry-ocr-'))
    try:
        prefix = temporary / 'page'
        run([shutil.which('pdftoppm'), '-f', '1', '-l', '20', '-r', '180', '-png',
             str(path), str(prefix)], timeout=180, output_limit=4000)
        return '\n\n'.join(ocr_image(image) for image in sorted(temporary.glob('page-*.png')))
    finally:
        shutil.rmtree(temporary)


def safe_xml(data):
    """Reject DTDs outright. Recent libexpat caps entity amplification, but the
    guard must not depend on which expat the host Python happens to link."""
    # A byte substring check misses UTF-16 declarations. Let the XML parser
    # decode the prolog and reject a DTD before it can expand any entities.
    from xml.parsers import expat
    def reject_declaration(*args):
        raise ValueError('The document declares a DTD or entities and was not parsed.')
    guard = expat.ParserCreate()
    guard.StartDoctypeDeclHandler = reject_declaration
    guard.EntityDeclHandler = reject_declaration
    try:
        guard.Parse(data, True)
        return ElementTree.fromstring(data)
    except (ElementTree.ParseError, expat.ExpatError) as exc:
        raise ValueError('The document contains invalid XML: ' + str(exc)) from None


def docx_text(path):
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo('word/document.xml')
        if info.file_size > MAX_TEXT * 4:
            raise ValueError('DOCX expanded content is too large.')
        root = safe_xml(archive.read(info))
    return ' '.join(node.text or '' for node in root.iter() if node.tag.endswith('}t'))


def extract(path):
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        text = pdf_text(path)
    elif suffix == '.docx':
        text = docx_text(path)
    elif suffix in {'.png', '.jpg', '.jpeg', '.tiff'}:
        text = ocr_image(path)
    else:
        text = path.read_text(encoding='utf-8', errors='replace')
    return text[:MAX_TEXT].replace('\x00', ' ')


def chunks(text, size=1400, overlap=180):
    clean = re.sub(r'[ \t]+', ' ', text)
    start = 0
    while start < len(clean):
        end = min(len(clean), start + size)
        if end < len(clean):
            boundary = max(clean.rfind('\n', start + size // 2, end), clean.rfind('. ', start + size // 2, end))
            if boundary > start:
                end = boundary + 1
        value = clean[start:end].strip()
        if value:
            yield value
        if end >= len(clean):
            break
        start = max(start + 1, end - overlap)


def rebuild(run_id=None):
    with lock:
        destination = database_path()
        temporary = destination.with_name('document-index-' + __import__('uuid').uuid4().hex + '.tmp')
        indexed = skipped = chunk_count = 0
        try:
            with sqlite3.connect(temporary) as connection:
                connection.execute('CREATE TABLE metadata(path TEXT PRIMARY KEY,bytes INTEGER,sha256 TEXT,indexed_at TEXT)')
                connection.execute("CREATE VIRTUAL TABLE chunks USING fts5(path UNINDEXED,chunk_id UNINDEXED,text,tokenize='unicode61')")
                for path in source_files():
                    if run_id:
                        db.event(run_id, 'status', 'Indexing ' + path.relative_to(config.DOCUMENTS).as_posix())
                    try:
                        text = extract(path)
                        if not text.strip():
                            skipped += 1
                            continue
                        relative_path = path.relative_to(config.DOCUMENTS).as_posix()
                        digest = hashlib.sha256(path.read_bytes()).hexdigest()
                        connection.execute('INSERT INTO metadata VALUES(?,?,?,?)',
                                           (relative_path, path.stat().st_size, digest, db.now()))
                        for number, value in enumerate(chunks(text), 1):
                            connection.execute('INSERT INTO chunks(path,chunk_id,text) VALUES(?,?,?)',
                                               (relative_path, number, value))
                            chunk_count += 1
                        indexed += 1
                    except Exception as exc:
                        skipped += 1
                        if run_id:
                            db.event(run_id, 'warning', f'Skipped {path.name}: {str(exc)[:300]}')
                connection.execute('CREATE TABLE state(key TEXT PRIMARY KEY,value TEXT)')
                connection.execute('INSERT INTO state VALUES(?,?)', ('summary', json.dumps({
                    'indexed_files': indexed, 'skipped_files': skipped, 'chunks': chunk_count,
                    'indexed_at': db.now()})))
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return status()


def status():
    path = database_path()
    base = {'folder': str(config.DOCUMENTS), 'indexed_files': 0, 'skipped_files': 0, 'chunks': 0,
            'indexed_at': None, 'ocr_available': bool(shutil.which('tesseract'))}
    if not path.exists():
        return base
    try:
        with sqlite3.connect(path) as connection:
            row = connection.execute("SELECT value FROM state WHERE key='summary'").fetchone()
        return {**base, **json.loads(row[0])} if row else base
    except (sqlite3.Error, json.JSONDecodeError):
        return base


def query(text, limit=8):
    terms = re.findall(r'[\w-]{2,}', text, flags=re.UNICODE)[:12]
    if not terms:
        return []
    path = database_path()
    if not path.exists():
        return []
    expression = ' AND '.join('"' + term.replace('"', '') + '"' for term in terms)
    with sqlite3.connect(path) as connection:
        rows = connection.execute('''SELECT path,chunk_id,
            snippet(chunks,2,'[',']',' … ',28),bm25(chunks) FROM chunks
            WHERE chunks MATCH ? ORDER BY bm25(chunks) LIMIT ?''', (expression, min(20, max(1, limit)))).fetchall()
    return [{'citation': f'{row[0]}#chunk-{row[1]}', 'path': row[0], 'chunk': row[1],
             'snippet': row[2], 'score': round(float(row[3]), 4)} for row in rows]


def read(path, chunk=None):
    if chunk is None:
        value = extract(relative(path))
        return value[:24000]
    with sqlite3.connect(database_path()) as connection:
        row = connection.execute('SELECT text FROM chunks WHERE path=? AND chunk_id=?', (path, int(chunk))).fetchone()
    if not row:
        raise ValueError('Indexed document chunk not found. Reindex the documents folder.')
    return row[0]
