import { useState, useEffect } from 'react';
import {
  Check,
  Copy,
  Download,
  Eye,
  EyeOff,
  FileCode2,
  HardDrive,
  KeyRound,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Table,
  Trash2,
  Upload,
  Zap,
} from 'lucide-react';
import { request } from '../api';
import './settings.css';

const DEFAULT_PRESETS = [
  { key: 'APP_ENV', value: 'development', scope: 'runtime', description: 'Application target environment' },
  { key: 'PORT', value: '5173', scope: 'runtime', description: 'Container web server port' },
  { key: 'LOG_LEVEL', value: 'debug', scope: 'runtime', description: 'Logger verbosity level' },
  { key: 'CORS_ALLOWED_ORIGINS', value: 'http://localhost:3000', scope: 'runtime', description: 'Allowed origins for CORS' },
  { key: 'ENABLE_CACHE', value: 'true', scope: 'runtime', description: 'Enable in-memory query caching' },
  { key: 'DB_POOL_SIZE', value: '10', scope: 'sandbox', description: 'Database connection pool max limit' },
  { key: 'VITE_API_BASE', value: '/api', scope: 'build', description: 'Vite client build-time API base' },
];

export default function SettingsPanel({ project, config, running, refresh, onOpenGlobalSettings }) {
  const [variables, setVariables] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [scopeFilter, setScopeFilter] = useState('all');
  const [viewMode, setViewMode] = useState('table'); // 'table' | 'raw'
  const [rawText, setRawText] = useState('');
  const [copiedKey, setCopiedKey] = useState(null);
  const [revealedKeys, setRevealedKeys] = useState(new Set());
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  // Form state
  const [keyInput, setKeyInput] = useState('');
  const [valInput, setValInput] = useState('');
  const [scopeInput, setScopeInput] = useState('runtime');
  const [descInput, setDescInput] = useState('');
  const [showFormVal, setShowFormVal] = useState(false);
  const [editingKey, setEditingKey] = useState(null);

  // App-specific dev options
  const [devPort, setDevPort] = useState('5173');
  const [autoRunChecks, setAutoRunChecks] = useState(true);

  useEffect(() => {
    loadEnv();
  }, [project.id]);

  async function loadEnv() {
    setLoading(true);
    setError('');
    try {
      const res = await request(`/projects/${project.id}/env`);
      setVariables(res.variables || []);
      setRawText(res.raw || '');
    } catch (err) {
      const fallback = project.env_vars || DEFAULT_PRESETS.slice(0, 4);
      setVariables(fallback);
      setRawText(formatRawEnv(fallback));
    } finally {
      setLoading(false);
    }
  }

  function formatRawEnv(vars) {
    return vars
      .map(v => `# ${v.description || v.scope}\n${v.key}=${v.value}`)
      .join('\n\n');
  }

  function showNotice(msg) {
    setNotice(msg);
    setTimeout(() => setNotice(''), 3500);
  }

  async function handleAddOrUpdate(e) {
    e?.preventDefault();
    setError('');

    const trimmedKey = keyInput.trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_');
    if (!trimmedKey) {
      setError('Please provide a valid variable name (e.g. PORT, LOG_LEVEL).');
      return;
    }

    const updated = [...variables.filter(v => v.key !== trimmedKey)];
    updated.push({
      key: trimmedKey,
      value: valInput,
      scope: scopeInput,
      description: descInput.trim() || undefined,
    });

    setVariables(updated);
    setRawText(formatRawEnv(updated));

    try {
      await request(`/projects/${project.id}/env`, { variables: updated });
      showNotice(editingKey ? `Updated ${trimmedKey}` : `Added ${trimmedKey}`);
      setKeyInput('');
      setValInput('');
      setDescInput('');
      setEditingKey(null);
      if (refresh) refresh();
    } catch (err) {
      setError(err.message || 'Failed to persist environment variable.');
    }
  }

  async function handleDelete(keyToDelete) {
    const updated = variables.filter(v => v.key !== keyToDelete);
    setVariables(updated);
    setRawText(formatRawEnv(updated));
    try {
      await request(`/projects/${project.id}/env/${keyToDelete}`, undefined, { method: 'DELETE' });
      showNotice(`Removed ${keyToDelete}`);
      if (refresh) refresh();
    } catch (err) {
      setError(err.message || 'Failed to remove variable.');
    }
  }

  function handleEdit(item) {
    setEditingKey(item.key);
    setKeyInput(item.key);
    setValInput(item.value);
    setScopeInput(item.scope || 'runtime');
    setDescInput(item.description || '');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function handleCancelEdit() {
    setEditingKey(null);
    setKeyInput('');
    setValInput('');
    setDescInput('');
  }

  function handlePresetClick(preset) {
    setKeyInput(preset.key);
    setValInput(preset.value);
    setScopeInput(preset.scope);
    setDescInput(preset.description);
    setEditingKey(null);
  }

  function toggleReveal(key) {
    const next = new Set(revealedKeys);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setRevealedKeys(next);
  }

  function copyValue(key, val) {
    navigator.clipboard.writeText(val);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  }

  async function handleApplyRawText() {
    setError('');
    const parsed = [];
    const lines = rawText.split('\n');
    let lastComment = '';

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;
      if (line.startsWith('#')) {
        lastComment = line.replace(/^#\s*/, '');
        continue;
      }
      const eqIdx = line.indexOf('=');
      if (eqIdx > 0) {
        const k = line.slice(0, eqIdx).trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_');
        const v = line.slice(eqIdx + 1).trim();
        parsed.push({
          key: k,
          value: v,
          scope: 'runtime',
          description: lastComment || undefined,
        });
        lastComment = '';
      }
    }

    if (!parsed.length) {
      setError('No valid KEY=VALUE definitions found in text.');
      return;
    }

    setVariables(parsed);
    try {
      await request(`/projects/${project.id}/env`, { variables: parsed });
      showNotice(`Successfully imported ${parsed.length} variables from .env`);
      setViewMode('table');
      if (refresh) refresh();
    } catch (err) {
      setError(err.message || 'Failed to save parsed variables.');
    }
  }

  function downloadEnvFile() {
    const blob = new Blob([rawText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${project.name.replace(/[^a-z0-9-]/gi, '-')}.env`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  const filtered = variables.filter(v => {
    const matchesSearch =
      v.key.toLowerCase().includes(search.toLowerCase()) ||
      v.value.toLowerCase().includes(search.toLowerCase()) ||
      (v.description || '').toLowerCase().includes(search.toLowerCase());
    const matchesScope = scopeFilter === 'all' || v.scope === scopeFilter;
    return matchesSearch && matchesScope;
  });

  const countRuntime = variables.filter(v => v.scope === 'runtime').length;
  const countBuild = variables.filter(v => v.scope === 'build').length;
  const countSandbox = variables.filter(v => v.scope === 'sandbox').length;

  return (
    <div className="tool-pane settings-pane">
      {/* Header */}
      <div className="settings-heading">
        <div>
          <span className="eyebrow">DEVELOPMENT APP SETTINGS</span>
          <h2>{project.name} Settings</h2>
          <p>
            Configure environment variables, container execution port, and sandbox variables
            specifically for the <strong>{project.name}</strong> application in development.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button onClick={loadEnv} disabled={loading} title="Reload environment variables">
            <RefreshCw size={14} className={loading ? 'spin' : ''} /> Refresh
          </button>
          <button className="primary" onClick={downloadEnvFile} title="Export variables to .env file">
            <Download size={14} /> Export .env
          </button>
        </div>
      </div>

      {/* Global Settings Hint Banner */}
      <div className="global-settings-hint-banner">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Settings size={15} color="#9ec5a0" />
          <span>
            Looking for studio-wide defaults, AI provider models, or local storage folders?
          </span>
        </div>
        {onOpenGlobalSettings && (
          <button
            type="button"
            className="action-btn"
            style={{ fontSize: '11px', padding: '4px 10px' }}
            onClick={onOpenGlobalSettings}>
            Open Global Settings
          </button>
        )}
      </div>

      {/* Notice Banner */}
      {notice && (
        <div className="notice-banner">
          <Check size={16} />
          <span>{notice}</span>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="mobile-error" style={{ margin: 0 }}>
          {error}
        </div>
      )}

      {/* Summary Cards */}
      <div className="settings-summary-grid">
        <div className="summary-card">
          <span className="val">{variables.length}</span>
          <span className="lbl">App Variables</span>
        </div>
        <div className="summary-card">
          <span className="val">{countRuntime}</span>
          <span className="lbl">Runtime (App)</span>
        </div>
        <div className="summary-card">
          <span className="val">{countBuild}</span>
          <span className="lbl">Build Scope</span>
        </div>
        <div className="summary-card">
          <span className="val">{countSandbox}</span>
          <span className="lbl">Sandbox / Docker</span>
        </div>
      </div>

      {/* Add / Edit Form Card */}
      <div className="settings-card">
        <div className="card-title-row">
          <h3>
            <Plus size={16} /> {editingKey ? `Edit Variable: ${editingKey}` : 'Add App Environment Variable'}
          </h3>
          {editingKey && (
            <button className="action-btn" onClick={handleCancelEdit}>
              Cancel Edit
            </button>
          )}
        </div>
        <p className="card-subtitle">
          Define variable name, value, and target injection scope for {project.name}.
        </p>

        <form onSubmit={handleAddOrUpdate}>
          <div className="env-form-grid">
            <div className="field-group">
              <label htmlFor="var-key">Variable Name</label>
              <input
                id="var-key"
                className="mono"
                placeholder="e.g. PORT, LOG_LEVEL"
                value={keyInput}
                onChange={e => setKeyInput(e.target.value.toUpperCase())}
                required
              />
            </div>

            <div className="field-group">
              <label htmlFor="var-val">Variable Value</label>
              <div className="input-with-action">
                <input
                  id="var-val"
                  type={showFormVal ? 'text' : 'password'}
                  className="mono"
                  placeholder="e.g. 8000, true, info"
                  value={valInput}
                  onChange={e => setValInput(e.target.value)}
                />
                <button
                  type="button"
                  tabIndex={-1}
                  aria-label={showFormVal ? 'Hide value' : 'Show value'}
                  onClick={() => setShowFormVal(!showFormVal)}>
                  {showFormVal ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <div className="field-group">
              <label htmlFor="var-scope">Injection Scope</label>
              <select
                id="var-scope"
                value={scopeInput}
                onChange={e => setScopeInput(e.target.value)}>
                <option value="runtime">Runtime (Application)</option>
                <option value="build">Build & Bundler</option>
                <option value="sandbox">Sandbox / Container</option>
              </select>
            </div>
          </div>

          <div className="env-form-row2" style={{ marginTop: '12px' }}>
            <div className="field-group">
              <label htmlFor="var-desc">Description (Optional)</label>
              <input
                id="var-desc"
                placeholder="e.g. Backend API port for local preview container"
                value={descInput}
                onChange={e => setDescInput(e.target.value)}
              />
            </div>
            <button type="submit" className="primary" style={{ height: '38px', padding: '0 20px' }}>
              {editingKey ? <Check size={14} /> : <Plus size={14} />}
              {editingKey ? 'Update Variable' : 'Add Variable'}
            </button>
          </div>
        </form>

        {/* Quick Presets */}
        <div className="presets-row">
          <span className="presets-label">App Presets:</span>
          {DEFAULT_PRESETS.map(p => (
            <button
              type="button"
              key={p.key}
              className="preset-chip"
              onClick={() => handlePresetClick(p)}
              title={`${p.description} (${p.value})`}>
              + {p.key}
            </button>
          ))}
        </div>
      </div>

      {/* Variables List Card */}
      <div className="settings-card">
        <div className="card-title-row">
          <h3>
            <KeyRound size={16} /> Configured Variables for {project.name} ({filtered.length})
          </h3>

          <div className="view-mode-toggle">
            <button
              className={viewMode === 'table' ? 'active' : ''}
              onClick={() => setViewMode('table')}>
              <Table size={13} /> Table
            </button>
            <button
              className={viewMode === 'raw' ? 'active' : ''}
              onClick={() => setViewMode('raw')}>
              <FileCode2 size={13} /> Raw .env
            </button>
          </div>
        </div>

        {viewMode === 'table' ? (
          <>
            {/* Filter / Search Bar */}
            <div className="filter-bar">
              <div className="search-box">
                <Search size={14} />
                <input
                  placeholder="Filter variables by name or value…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                />
              </div>

              <div className="scope-pills">
                {['all', 'runtime', 'build', 'sandbox'].map(s => (
                  <button
                    key={s}
                    className={`scope-pill-btn ${scopeFilter === s ? 'active' : ''}`}
                    onClick={() => setScopeFilter(s)}>
                    {s.charAt(0).toUpperCase() + s.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Table */}
            <div className="env-table-container">
              <table className="env-table">
                <thead>
                  <tr>
                    <th style={{ width: '220px' }}>Variable</th>
                    <th style={{ width: '100px' }}>Scope</th>
                    <th>Value</th>
                    <th>Description</th>
                    <th style={{ width: '90px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.length ? (
                    filtered.map(item => {
                      const isRevealed = revealedKeys.has(item.key);
                      const isCopied = copiedKey === item.key;
                      return (
                        <tr key={item.key}>
                          <td>
                            <span className="key-badge">{item.key}</span>
                          </td>
                          <td>
                            <span className={`scope-badge ${item.scope || 'runtime'}`}>
                              {item.scope || 'runtime'}
                            </span>
                          </td>
                          <td>
                            <div className="value-cell">
                              <span className="value-text">
                                {isRevealed ? item.value : '••••••••••••'}
                              </span>
                              <button
                                className="action-btn"
                                title={isRevealed ? 'Mask value' : 'Reveal value'}
                                onClick={() => toggleReveal(item.key)}>
                                {isRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                              </button>
                              <button
                                className="action-btn"
                                title="Copy value to clipboard"
                                onClick={() => copyValue(item.key, item.value)}>
                                {isCopied ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
                              </button>
                            </div>
                          </td>
                          <td>
                            <span className="desc-text">
                              {item.description || '—'}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <div style={{ display: 'inline-flex', gap: '4px' }}>
                              <button
                                className="action-btn"
                                title={`Edit ${item.key}`}
                                onClick={() => handleEdit(item)}>
                                <SlidersHorizontal size={13} />
                              </button>
                              <button
                                className="action-btn delete"
                                title={`Delete ${item.key}`}
                                onClick={() => handleDelete(item.key)}>
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={5}>
                        <div className="empty-table">
                          <KeyRound size={28} />
                          <span>No environment variables match the search filter.</span>
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          /* Raw .env Editor View */
          <div className="raw-env-editor">
            <p className="card-subtitle">
              Edit in standard `.env` format. Comments starting with `#` are preserved as descriptions.
            </p>
            <textarea
              className="raw-env-textarea"
              value={rawText}
              onChange={e => setRawText(e.target.value)}
              placeholder="KEY=VALUE"
              spellCheck="false"
            />
            <div className="raw-env-actions">
              <button
                className="action-btn"
                onClick={() => {
                  navigator.clipboard.writeText(rawText);
                  showNotice('Copied .env content to clipboard');
                }}>
                  <Copy size={13} /> Copy .env
              </button>

              <div className="btn-group">
                <button onClick={() => setRawText(formatRawEnv(variables))}>
                  Reset to Current
                </button>
                <button className="primary" onClick={handleApplyRawText}>
                  <Check size={14} /> Parse & Apply Changes
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* App Runtime & Deployment Details */}
      <div className="settings-card">
        <div className="card-title-row">
          <h3>
            <Layers size={16} /> App Runtime & Development Configuration
          </h3>
          <span className="verified-label" style={{ margin: 0 }}>
            <ShieldCheck size={13} /> Sandbox Protected
          </span>
        </div>
        <p className="card-subtitle">
          Runtime environment, port mapping, and build options for this application.
        </p>

        <div className="studio-grid">
          <div className="field-group">
            <label>App Web Server Port</label>
            <input
              className="mono"
              value={devPort}
              onChange={e => setDevPort(e.target.value)}
              placeholder="5173"
            />
          </div>

          <div className="field-group">
            <label>App Workspace ID</label>
            <input
              className="mono"
              value={project.id}
              disabled
              style={{ opacity: 0.7 }}
            />
          </div>

          <div className="field-group">
            <label>Preview Sandbox Status</label>
            <div className="mono-info-box" style={{ background: '#111b14', padding: '8px 12px', borderRadius: '6px', border: '1px solid #233426' }}>
              <span className="status-dot" style={{ display: 'inline-block', width: '7px', height: '7px', borderRadius: '50%', background: project.preview_url ? '#22c55e' : '#f59e0b', marginRight: '6px' }} />
              <span style={{ fontSize: '12px', color: '#b9ccb7' }}>
                {project.preview_url ? `Running at ${project.preview_url}` : 'Container stopped / ready to launch'}
              </span>
            </div>
          </div>

          <div className="field-group">
            <label>Application Framework Stack</label>
            <div className="mono-info-box" style={{ background: '#111b14', padding: '8px 12px', borderRadius: '6px', border: '1px solid #233426' }}>
              <span style={{ fontSize: '12px', color: '#b9ccb7' }}>
                React 18 · Vite · Express · PostgreSQL · Tailwind CSS
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
