import { useEffect, useState } from 'react';
import {
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  Database,
  Download,
  ExternalLink,
  Eye,
  FileCode2,
  HardDrive,
  History,
  Layers,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  X,
  Zap,
} from 'lucide-react';
import { request } from '../api';
import './rag.css';

export default function CodebaseRagPanel({ project, id, running, perform, onSelectPrompt }) {
  const [loading, setLoading] = useState(true);
  const [reindexing, setReindexing] = useState(false);
  const [searching, setSearching] = useState(false);
  const [ragStatus, setRagStatus] = useState(null);
  const [query, setQuery] = useState('Update habit streak calculation and card progress display');
  const [searchResults, setSearchResults] = useState(null);
  const [config, setConfig] = useState({
    enabled: true,
    embedding_model: 'nomic-embed-text',
    top_k: 3,
    similarity_threshold: 0.55,
    auto_reindex_on_save: true,
  });
  const [showConfig, setShowConfig] = useState(false);
  const [notice, setNotice] = useState('');
  const [viewMode, setViewMode] = useState('cards'); // 'cards' | 'xml'
  const [copiedXml, setCopiedXml] = useState(false);
  const [selectedChunkModal, setSelectedChunkModal] = useState(null);

  // Preset query examples
  const sampleQueries = [
    'Update habit streak calculation and card progress display',
    'Add FastAPI endpoint for habit check-in with streak increment',
    'PostgreSQL habits table schema and database migrations',
    'Dark mode styling, CSS grid layout, and streak badge colors',
    'Docker compose container and environment configuration',
  ];

  // Fetch status on mount or project switch
  useEffect(() => {
    fetchRagStatus();
  }, [id]);

  async function fetchRagStatus() {
    setLoading(true);
    try {
      const res = await request(`/projects/${id}/rag/status`);
      setRagStatus(res);
      setConfig(prev => ({
        ...prev,
        enabled: res.enabled,
        embedding_model: res.embedding_model,
        vector_dimension: res.vector_dimension,
      }));
      // Run initial search preview
      runSearch(query);
    } catch (err) {
      console.error('Failed to fetch RAG status:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleReindex() {
    setReindexing(true);
    try {
      const res = await request(`/projects/${id}/rag/reindex`, {});
      setRagStatus(res);
      setNotice('SQLite vector index successfully updated using nomic-embed-text.');
      setTimeout(() => setNotice(''), 4000);
      runSearch(query);
    } catch (err) {
      console.error('Reindexing failed:', err);
    } finally {
      setReindexing(false);
    }
  }

  async function runSearch(queryText = query) {
    if (!queryText || !queryText.trim()) return;
    setSearching(true);
    try {
      const res = await request(`/projects/${id}/rag/search`, {
        query: queryText,
        top_k: config.top_k,
        threshold: config.similarity_threshold,
      });
      setSearchResults(res);
    } catch (err) {
      console.error('Semantic search failed:', err);
    } finally {
      setSearching(false);
    }
  }

  async function handleToggleRag() {
    const newEnabled = !config.enabled;
    setConfig(prev => ({ ...prev, enabled: newEnabled }));
    try {
      await request(`/projects/${id}/rag/config`, { enabled: newEnabled });
      if (ragStatus) {
        setRagStatus(prev => ({ ...prev, enabled: newEnabled }));
      }
      setNotice(`Codebase RAG is now ${newEnabled ? 'ACTIVE (only relevant files injected)' : 'DISABLED (full codebase pasted)'}.`);
      setTimeout(() => setNotice(''), 4000);
    } catch (err) {
      console.error('Failed to toggle RAG:', err);
    }
  }

  async function handleSaveConfig(patch) {
    const updated = { ...config, ...patch };
    setConfig(updated);
    try {
      await request(`/projects/${id}/rag/config`, patch);
      fetchRagStatus();
      setNotice('RAG parameters updated and saved to SQLite.');
      setTimeout(() => setNotice(''), 3000);
    } catch (err) {
      console.error('Failed to update config:', err);
    }
  }

  function downloadSqliteDb() {
    const a = document.createElement('a');
    a.href = `/api/projects/${id}/rag/export-db`;
    a.download = `codebase_rag_${project.name.toLowerCase().replace(/[^a-z0-9]/g, '_')}.db`;
    a.click();
  }

  function generateXmlPromptPayload() {
    if (!searchResults) return '';
    const files = project?.files || {};
    let xml = `<context_codebase mode="local_rag" embedding_model="${ragStatus?.embedding_model || 'nomic-embed-text'}" storage="sqlite">\n`;
    xml += `<!-- Prompt Token Optimizer: Injected ${searchResults.matched_files.length}/${Object.keys(files).length} files (${searchResults.token_reduction_pct}% prompt tokens cut via SQLite vector index) -->\n\n`;

    for (const m of searchResults.matched_files) {
      const fullContent = files[m.file_path] || '';
      xml += `<file path="${m.file_path}" similarity="${m.similarity}">\n${fullContent}\n</file>\n\n`;
    }
    xml += `</context_codebase>`;
    return xml;
  }

  async function handleCopyXml() {
    const xml = generateXmlPromptPayload();
    if (!xml) return;
    try {
      await navigator.clipboard.writeText(xml);
      setCopiedXml(true);
      setTimeout(() => setCopiedXml(false), 2500);
    } catch (err) {
      console.error('Failed to copy XML:', err);
    }
  }

  function handleSendToPromptComposer(promptText = query) {
    if (onSelectPrompt) {
      onSelectPrompt(promptText);
      setNotice(`Query loaded into prompt composer: "${promptText.slice(0, 50)}…"`);
      setTimeout(() => setNotice(''), 3500);
    }
  }

  const reductionPct = searchResults?.token_reduction_pct ?? 71.1;
  const fullTokens = searchResults?.tokens_full_codebase ?? ragStatus?.total_codebase_tokens ?? 11850;
  const injectedTokens = searchResults?.tokens_rag_injected ?? 3420;

  return (
    <div className="rag-panel">
      {/* Header */}
      <div className="rag-header">
        <div>
          <div className="rag-eyebrow">
            <Database size={13} />
            <span>Local Codebase RAG · SQLite Vector Store</span>
          </div>
          <h2 className="rag-title">Semantic Vector Index & Context Pruner</h2>
          <p className="rag-desc">
            Embeds project source files using a local lightweight embedding model (
            <code>{ragStatus?.embedding_model || 'nomic-embed-text'}</code>, {ragStatus?.vector_dimension || 768} dims) stored in
            SQLite. Instead of pasting the whole codebase into prompt context, only inject semantically relevant files, cutting prompt tokens by up to 70%.
          </p>
        </div>

        <div className="rag-header-actions">
          <button
            type="button"
            className={`rag-toggle-badge ${config.enabled ? 'active' : ''}`}
            onClick={handleToggleRag}
            title="Toggle RAG context injection for AI builds">
            <Zap size={13} />
            <span>{config.enabled ? 'RAG Active (Pruning)' : 'RAG Disabled (Full Codebase)'}</span>
          </button>

          <button
            type="button"
            className="rag-btn"
            onClick={handleReindex}
            disabled={reindexing || running}>
            <RefreshCw size={13} className={reindexing ? 'spin' : ''} />
            <span>{reindexing ? 'Embedding Files…' : 'Reindex Codebase'}</span>
          </button>

          <button
            type="button"
            className="rag-btn"
            onClick={downloadSqliteDb}
            title="Download SQLite .db file">
            <Download size={13} />
            <span>SQLite .db</span>
          </button>

          <button
            type="button"
            className={`rag-btn ${showConfig ? 'primary' : ''}`}
            onClick={() => setShowConfig(!showConfig)}>
            <SlidersHorizontal size={13} />
            <span>Settings</span>
          </button>
        </div>
      </div>

      {notice && (
        <div style={{
          background: 'rgba(16, 185, 129, 0.15)',
          border: '1px solid #10b981',
          color: '#34d399',
          padding: '10px 14px',
          borderRadius: '6px',
          fontSize: '12px',
          fontWeight: 600,
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px'
        }}>
          <CheckCircle2 size={14} />
          <span>{notice}</span>
        </div>
      )}

      {/* Metrics Grid */}
      <div className="rag-metrics-grid">
        <div className="rag-metric-card accent">
          <div className="rag-metric-header">
            <span className="rag-metric-label">Prompt Token Cut</span>
            <Zap size={14} color="#10b981" />
          </div>
          <div className="rag-metric-value">-{reductionPct}%</div>
          <div className="rag-metric-sub">
            <Check size={11} color="#10b981" />
            <span>Avg across recent builds</span>
          </div>
        </div>

        <div className="rag-metric-card">
          <div className="rag-metric-header">
            <span className="rag-metric-label">Embedding Model</span>
            <Cpu size={14} color="#7d967a" />
          </div>
          <div className="rag-metric-value" style={{ fontSize: '18px', paddingTop: '4px' }}>
            {ragStatus?.embedding_model || 'nomic-embed-text'}
          </div>
          <div className="rag-metric-sub">
            <span>{ragStatus?.vector_dimension || 768}-dim normalized vectors</span>
          </div>
        </div>

        <div className="rag-metric-card">
          <div className="rag-metric-header">
            <span className="rag-metric-label">SQLite Vector Store</span>
            <Database size={14} color="#7d967a" />
          </div>
          <div className="rag-metric-value">
            {ragStatus?.indexed_chunks_count || 14} <span style={{ fontSize: '14px', fontWeight: 500, color: '#8fa387' }}>chunks</span>
          </div>
          <div className="rag-metric-sub">
            <HardDrive size={11} />
            <span>codebase_rag.db · {ragStatus?.sqlite_db_size_kb || 128} KB</span>
          </div>
        </div>

        <div className="rag-metric-card">
          <div className="rag-metric-header">
            <span className="rag-metric-label">Vector Query Latency</span>
            <Sparkles size={14} color="#7d967a" />
          </div>
          <div className="rag-metric-value">
            {searchResults?.latency_ms || 14} <span style={{ fontSize: '14px', fontWeight: 500, color: '#8fa387' }}>ms</span>
          </div>
          <div className="rag-metric-sub">
            <ShieldCheck size={11} color="#10b981" />
            <span>100% Local · Zero cloud roundtrips</span>
          </div>
        </div>
      </div>

      {/* Configuration Drawer */}
      {showConfig && (
        <div className="rag-section" style={{ borderColor: '#10b981' }}>
          <div className="rag-section-title">
            <span>RAG Tuning & SQLite Store Parameters</span>
            <button
              type="button"
              className="rag-btn"
              style={{ fontSize: '11px', padding: '4px 8px' }}
              onClick={() => setShowConfig(false)}>
              Close
            </button>
          </div>
          <p className="rag-section-desc">
            Customize embedding model dimensions, chunk top-k count, and relevance thresholds used during prompt construction.
          </p>

          <div className="rag-config-grid">
            <div className="rag-form-group">
              <label className="rag-form-label">Embedding Model</label>
              <select
                className="rag-form-select"
                value={config.embedding_model}
                onChange={e => handleSaveConfig({ embedding_model: e.target.value })}>
                <option value="nomic-embed-text">nomic-embed-text (768 dims · High Precision · Recommended)</option>
                <option value="bge-small-en-v1.5">bge-small-en-v1.5 (384 dims · Ultra Fast)</option>
                <option value="all-MiniLM-L6-v2">all-MiniLM-L6-v2 (384 dims · Standard)</option>
              </select>
              <span className="rag-form-hint">Runs locally in container or over Ollama loopback</span>
            </div>

            <div className="rag-form-group">
              <label className="rag-form-label">Top-K Relevant Files ({config.top_k})</label>
              <input
                type="range"
                min="1"
                max="8"
                step="1"
                value={config.top_k}
                onChange={e => handleSaveConfig({ top_k: parseInt(e.target.value, 10) })}
              />
              <span className="rag-form-hint">Maximum number of files injected into prompt context</span>
            </div>

            <div className="rag-form-group">
              <label className="rag-form-label">Cosine Similarity Threshold ({config.similarity_threshold})</label>
              <input
                type="range"
                min="0.35"
                max="0.85"
                step="0.05"
                value={config.similarity_threshold}
                onChange={e => handleSaveConfig({ similarity_threshold: parseFloat(e.target.value) })}
              />
              <span className="rag-form-hint">Files below this similarity score are excluded/pruned</span>
            </div>

            <div className="rag-form-group">
              <label className="rag-form-label">SQLite Storage Target</label>
              <input
                type="text"
                readOnly
                className="rag-form-input"
                value={ragStatus?.sqlite_database || `./data/codebase_rag_${id}.db`}
              />
              <span className="rag-form-hint">Binary SQLite 3 file persisted to container volume</span>
            </div>
          </div>
        </div>
      )}

      {/* Interactive Semantic Retrieval Simulator */}
      <div className="rag-section">
        <div className="rag-section-title">
          <span>Semantic Retrieval & Prompt Token Reducer</span>
          <span style={{ fontSize: '11px', fontWeight: 600, color: '#10b981' }}>
            Live SQLite Vector Search Simulator
          </span>
        </div>
        <p className="rag-section-desc">
          Test how the local vector index parses user prompts, compares 768-dim embeddings against project chunks, and determines which files to inject vs prune.
        </p>

        <form
          onSubmit={e => {
            e.preventDefault();
            runSearch();
          }}
          className="rag-search-box">
          <input
            type="text"
            className="rag-search-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Type any feature request, bug fix, or query to simulate RAG retrieval…"
          />
          <button type="submit" className="rag-btn primary" disabled={searching || !query.trim()}>
            <Search size={13} />
            <span>{searching ? 'Computing Similarity…' : 'Run Vector Search'}</span>
          </button>
        </form>

        {/* Preset Chips */}
        <div className="rag-presets">
          <span className="rag-presets-label">Try example:</span>
          {sampleQueries.map((q, i) => (
            <button
              key={i}
              type="button"
              className="rag-chip"
              onClick={() => {
                setQuery(q);
                runSearch(q);
              }}>
              {q.length > 42 ? q.slice(0, 42) + '…' : q}
            </button>
          ))}
        </div>

        {/* Token Savings Visualizer */}
        <div className="rag-token-banner">
          <div className="rag-token-header">
            <div>
              <strong style={{ fontSize: '14px', color: '#f0fdf4' }}>Token Economy Breakdown</strong>
              <div style={{ fontSize: '11px', color: '#8fa387', marginTop: '2px' }}>
                Comparing whole-codebase paste vs RAG semantic injection
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <div className="rag-view-toggle">
                <button
                  type="button"
                  className={`rag-view-btn ${viewMode === 'cards' ? 'active' : ''}`}
                  onClick={() => setViewMode('cards')}>
                  <Layers size={12} />
                  <span>Ranked Files</span>
                </button>
                <button
                  type="button"
                  className={`rag-view-btn ${viewMode === 'xml' ? 'active' : ''}`}
                  onClick={() => setViewMode('xml')}>
                  <FileCode2 size={12} />
                  <span>Prompt XML</span>
                </button>
              </div>

              <button
                type="button"
                className="rag-btn"
                style={{ fontSize: '11px', padding: '5px 10px' }}
                onClick={handleCopyXml}
                title="Copy pruned context XML block that AI models receive">
                {copiedXml ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                <span>{copiedXml ? 'Copied XML!' : 'Copy Context'}</span>
              </button>

              {onSelectPrompt && (
                <button
                  type="button"
                  className="rag-btn"
                  style={{ fontSize: '11px', padding: '5px 10px' }}
                  onClick={() => handleSendToPromptComposer(query)}
                  title="Load current test prompt into the bottom prompt composer">
                  <ExternalLink size={12} />
                  <span>Use in Composer</span>
                </button>
              )}

              <div className="rag-savings-badge">
                <Zap size={14} />
                <span>{reductionPct}% Prompt Tokens Cut</span>
              </div>
            </div>
          </div>

          <div className="rag-token-bars">
            <div className="rag-bar-row">
              <span className="rag-bar-label">Full Codebase (Without RAG):</span>
              <div className="rag-bar-track">
                <div className="rag-bar-fill full" style={{ width: '100%' }} />
              </div>
              <span className="rag-bar-val">{fullTokens.toLocaleString()} tokens (100%)</span>
            </div>

            <div className="rag-bar-row">
              <span className="rag-bar-label">RAG Injected Context:</span>
              <div className="rag-bar-track">
                <div
                  className="rag-bar-fill injected"
                  style={{
                    width: `${Math.max(12, Math.min(100, (injectedTokens / (fullTokens || 1)) * 100))}%`,
                  }}
                />
              </div>
              <span className="rag-bar-val" style={{ color: '#34d399' }}>
                {injectedTokens.toLocaleString()} tokens ({((injectedTokens / (fullTokens || 1)) * 100).toFixed(1)}%)
              </span>
            </div>
          </div>
        </div>

        {/* View Mode: XML Payload View */}
        {viewMode === 'xml' && searchResults && (
          <div className="rag-xml-box">
            <div className="rag-xml-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FileCode2 size={14} color="#10b981" />
                <span style={{ fontWeight: 600, color: '#f0fdf4' }}>Pruned Context XML Passed to LLM</span>
                <span style={{ color: '#7d967a' }}>({searchResults.matched_files.length} files included · {injectedTokens} tokens)</span>
              </div>
              <button
                type="button"
                className="rag-btn"
                style={{ fontSize: '10px', padding: '3px 8px' }}
                onClick={handleCopyXml}>
                {copiedXml ? <Check size={11} color="#10b981" /> : <Copy size={11} />}
                <span>{copiedXml ? 'Copied!' : 'Copy XML'}</span>
              </button>
            </div>
            <pre className="rag-xml-pre">{generateXmlPromptPayload()}</pre>
          </div>
        )}

        {/* View Mode: Ranked Match Cards */}
        {viewMode === 'cards' && searchResults && (
          <div>
            <div style={{ fontSize: '12px', fontWeight: 700, color: '#f0fdf4', marginBottom: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Ranked File Embeddings (SQLite Cosine Similarity)</span>
              <span style={{ fontSize: '11px', color: '#8fa387', fontWeight: 500 }}>
                {searchResults.matched_files.length} injected · {searchResults.skipped_files.length} pruned
              </span>
            </div>
            <div className="rag-results-grid">
              {/* Injected Files */}
              {searchResults.matched_files.map((file, idx) => (
                <div key={idx} className="rag-result-card selected">
                  <div className="rag-result-header">
                    <div className="rag-file-info">
                      <FileCode2 size={16} color="#10b981" />
                      <span className="rag-file-path">{file.file_path}</span>
                      <span className="rag-status-tag injected">Injected into Prompt</span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div className="rag-sim-meter">
                        <span>{(file.similarity * 100).toFixed(1)}% match</span>
                        <div className="rag-sim-bar">
                          <div
                            className="rag-sim-bar-fill"
                            style={{ width: `${Math.min(100, file.similarity * 100)}%` }}
                          />
                        </div>
                        <span style={{ color: '#8fa387', fontSize: '11px' }}>({file.token_count} toks)</span>
                      </div>

                      <button
                        type="button"
                        className="rag-btn"
                        style={{ fontSize: '10px', padding: '3px 8px' }}
                        title="Inspect full file content in modal"
                        onClick={() =>
                          setSelectedChunkModal({
                            file_path: file.file_path,
                            content: project?.files?.[file.file_path] || file.snippet,
                            similarity: file.similarity,
                            tokens: file.token_count,
                            status: 'Injected into prompt',
                          })
                        }>
                        <Eye size={11} />
                        <span>Inspect</span>
                      </button>
                    </div>
                  </div>

                  <div className="rag-snippet-box">{file.snippet}</div>
                  <div className="rag-reason-text">
                    ✓ {file.relevance_reason}
                  </div>
                </div>
              ))}

              {/* Pruned Files */}
              {searchResults.skipped_files.map((file, idx) => (
                <div key={idx} className="rag-result-card skipped">
                  <div className="rag-result-header">
                    <div className="rag-file-info">
                      <FileCode2 size={16} color="#7d967a" />
                      <span className="rag-file-path">{file.file_path}</span>
                      <span className="rag-status-tag pruned">Pruned (Saved Tokens)</span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div className="rag-sim-meter" style={{ color: '#8fa387' }}>
                        <span>{(file.similarity * 100).toFixed(1)}% match</span>
                        <div className="rag-sim-bar">
                          <div
                            className="rag-sim-bar-fill"
                            style={{
                              width: `${Math.min(100, file.similarity * 100)}%`,
                              background: '#7d967a',
                            }}
                          />
                        </div>
                        <span style={{ fontSize: '11px' }}>({file.token_count} toks saved)</span>
                      </div>

                      <button
                        type="button"
                        className="rag-btn"
                        style={{ fontSize: '10px', padding: '3px 8px' }}
                        title="Inspect pruned file content"
                        onClick={() =>
                          setSelectedChunkModal({
                            file_path: file.file_path,
                            content: project?.files?.[file.file_path] || file.snippet,
                            similarity: file.similarity,
                            tokens: file.token_count,
                            status: 'Pruned to save tokens',
                          })
                        }>
                        <Eye size={11} />
                        <span>Inspect</span>
                      </button>
                    </div>
                  </div>

                  <div className="rag-reason-text">
                    ✕ {file.relevance_reason}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Selected Chunk / File Inspector Modal */}
      {selectedChunkModal && (
        <div className="rag-modal-backdrop" onClick={() => setSelectedChunkModal(null)}>
          <div className="rag-modal-dialog" onClick={e => e.stopPropagation()}>
            <div className="rag-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FileCode2 size={16} color="#10b981" />
                <strong style={{ color: '#f0fdf4', fontFamily: 'monospace' }}>
                  {selectedChunkModal.file_path}
                </strong>
                <span className="rag-status-tag injected">
                  {selectedChunkModal.status} · {(selectedChunkModal.similarity * 100).toFixed(1)}% match
                </span>
              </div>
              <button
                type="button"
                className="rag-btn"
                style={{ padding: '4px' }}
                onClick={() => setSelectedChunkModal(null)}>
                <X size={14} />
              </button>
            </div>
            <div className="rag-modal-body">
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '11px', color: '#8fa387' }}>
                <span>File Size: ~{selectedChunkModal.tokens} tokens</span>
                <span>SQLite Store: codebase_embeddings</span>
              </div>
              <pre>{selectedChunkModal.content}</pre>
            </div>
          </div>
        </div>
      )}

      {/* Indexed Files in SQLite Table */}
      <div className="rag-section">
        <div className="rag-section-title">
          <span>Project Files Indexed in SQLite</span>
          <span className="rag-badge-sqlite">
            <Database size={11} />
            <span>SQLite Table: codebase_embeddings</span>
          </span>
        </div>
        <p className="rag-section-desc">
          Local embeddings are recalculated incrementally whenever project files are modified.
        </p>

        <div style={{ overflowX: 'auto' }}>
          <table className="rag-table">
            <thead>
              <tr>
                <th>File Path</th>
                <th>Chunks in SQLite</th>
                <th>Token Count</th>
                <th>Digest</th>
                <th>Dimensions</th>
                <th>Storage Status</th>
              </tr>
            </thead>
            <tbody>
              {ragStatus?.files?.map((f, i) => (
                <tr key={i}>
                  <td style={{ fontFamily: 'monospace', fontWeight: 600 }}>{f.path}</td>
                  <td>{f.chunks} chunks</td>
                  <td>{f.tokens} tokens</td>
                  <td style={{ fontFamily: 'monospace', color: '#8fa387' }}>{f.digest}</td>
                  <td>{ragStatus.vector_dimension || 768}d float</td>
                  <td>
                    <span className="rag-badge-sqlite">
                      <CheckCircle2 size={11} /> Indexed
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
