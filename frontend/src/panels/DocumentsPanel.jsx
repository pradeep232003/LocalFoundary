import { BookOpen, RefreshCw, Search } from 'lucide-react';

export default function DocumentsPanel({
  project,
  id,
  running,
  busy,
  perform,
  launch,
  searchDocuments,
  documentQuery,
  setDocumentQuery,
  documentResults,
}) {
  return (
    <div className="tool-pane">
      <div className="data-heading">
        <div>
          <span className="eyebrow">LOCAL KNOWLEDGE</span>
          <h2>Search with citations.</h2>
          <p>
            Index text, code, DOCX, and PDF files from the managed documents folder. Image and scanned-PDF OCR
            is used when Tesseract and Poppler are installed.
          </p>
        </div>
        <button
          className="primary"
          disabled={running}
          onClick={() => perform(() => launch(`/projects/${id}/documents/reindex`))}>
          <RefreshCw size={14} /> Reindex
        </button>
      </div>
      <div className="folder-card">
        <BookOpen size={18} />
        <div>
          <strong>
            {project.documents.indexed_files} files · {project.documents.chunks} chunks
          </strong>
          <small>{project.documents.folder}</small>
        </div>
        <span>{project.documents.ocr_available ? 'OCR ready' : 'Text extraction'}</span>
      </div>
      <form className="document-search" onSubmit={searchDocuments}>
        <input
          aria-label="Search local documents"
          value={documentQuery}
          onChange={e => setDocumentQuery(e.target.value)}
          placeholder="Search indexed documents…"
        />
        <button disabled={busy || !documentQuery.trim()}>
          <Search size={14} /> Search
        </button>
      </form>
      <div className="document-results">
        {documentResults.length ? (
          documentResults.map(result => (
            <article key={result.citation}>
              <strong>{result.citation}</strong>
              <p>{result.snippet}</p>
            </article>
          ))
        ) : (
          <div className="backup-empty">
            Search directly, or choose the Documents agent in chat for a cited synthesis.
          </div>
        )}
      </div>
    </div>
  );
}
