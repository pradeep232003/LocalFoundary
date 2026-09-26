import { useState } from 'react';
import {
  Activity,
  Bot,
  Check,
  CircleDollarSign,
  Cpu,
  Folder,
  HardDrive,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  WifiOff,
  X,
  Zap,
} from 'lucide-react';

export default function GlobalSettingsModal({
  config,
  provider,
  setProvider,
  budget,
  setBudget,
  maxInput,
  setMaxInput,
  maxOutput,
  setMaxOutput,
  buildOptions,
  setBuildOptions,
  onClose,
  onShowDiagnostics,
  onSaveNotice,
}) {
  const [activeSection, setActiveSection] = useState('providers');
  const [offlineOnly, setOfflineOnly] = useState(config?.offline_only || false);
  const [localVision, setLocalVision] = useState(config?.local_vision || false);
  const [localApiBase, setLocalApiBase] = useState('http://127.0.0.1:11434/v1');
  const [defaultProvider, setDefaultProvider] = useState(provider);
  const [globalBudget, setGlobalBudget] = useState(budget);
  const [globalMaxInput, setGlobalMaxInput] = useState(maxInput);
  const [globalMaxOutput, setGlobalMaxOutput] = useState(maxOutput);
  const [maxRepairs, setMaxRepairs] = useState(buildOptions.max_repairs);
  const [browserChecks, setBrowserChecks] = useState(buildOptions.browser_checks);
  const [saved, setSaved] = useState(false);

  function handleSave(e) {
    e.preventDefault();
    setProvider(defaultProvider);
    setBudget(globalBudget);
    setMaxInput(globalMaxInput);
    setMaxOutput(globalMaxOutput);
    setBuildOptions(prev => ({
      ...prev,
      max_repairs: Number(maxRepairs),
      browser_checks: Boolean(browserChecks),
    }));

    setSaved(true);
    if (onSaveNotice) {
      onSaveNotice('Local Foundry global settings saved successfully.');
    }
    setTimeout(() => {
      onClose();
    }, 400);
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal global-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="global-settings-title"
        onClick={e => e.stopPropagation()}>
        <button
          type="button"
          className="icon-button modal-close"
          aria-label="Close settings"
          onClick={onClose}>
          <X size={16} />
        </button>

        <div className="global-settings-header">
          <div className="modal-icon">
            <Settings size={22} />
          </div>
          <div>
            <span className="global-settings-eyebrow">LOCAL FOUNDRY STUDIO</span>
            <h2 id="global-settings-title">Global Settings</h2>
          </div>
        </div>

        <p className="global-settings-desc">
          Configure studio-wide settings, default AI provider endpoints, build token limits, offline
          isolation, and storage locations across all projects.
        </p>

        {/* Section Navigation Tabs */}
        <div className="global-settings-nav" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeSection === 'providers'}
            className={activeSection === 'providers' ? 'active' : ''}
            onClick={() => setActiveSection('providers')}>
            <Zap size={14} /> AI Providers
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSection === 'limits'}
            className={activeSection === 'limits' ? 'active' : ''}
            onClick={() => setActiveSection('limits')}>
            <SlidersHorizontal size={14} /> Build Limits
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSection === 'privacy'}
            className={activeSection === 'privacy' ? 'active' : ''}
            onClick={() => setActiveSection('privacy')}>
            <ShieldCheck size={14} /> Privacy & Offline
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSection === 'workspace'}
            className={activeSection === 'workspace' ? 'active' : ''}
            onClick={() => setActiveSection('workspace')}>
            <HardDrive size={14} /> Storage & System
          </button>
        </div>

        <form onSubmit={handleSave} className="global-settings-body">
          {/* 1. AI Providers Section */}
          {activeSection === 'providers' && (
            <div className="settings-section-pane">
              <div className="field-group">
                <label htmlFor="global-provider-select">DEFAULT AI MODEL PROVIDER</label>
                <select
                  id="global-provider-select"
                  value={defaultProvider}
                  onChange={e => setDefaultProvider(e.target.value)}>
                  <option value="anthropic">Claude (Anthropic · claude-3-7-sonnet)</option>
                  <option value="openai">OpenAI (gpt-4o)</option>
                  <option value="local">Local AI (Ollama / vLLM Loopback · Free)</option>
                </select>
                <small className="field-hint">
                  Selected provider will be set as the default across workspace chats and builds.
                </small>
              </div>

              <div className="field-group">
                <label htmlFor="global-local-url">LOCAL AI SERVER LOOPBACK URL</label>
                <input
                  id="global-local-url"
                  className="mono"
                  value={localApiBase}
                  onChange={e => setLocalApiBase(e.target.value)}
                  placeholder="http://127.0.0.1:11434/v1"
                />
                <small className="field-hint">
                  Compatible with Ollama, LM Studio, llama.cpp, and vLLM local endpoints.
                </small>
              </div>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={localVision}
                  onChange={e => setLocalVision(e.target.checked)}
                />
                <div>
                  <strong>Local Model Vision Processing</strong>
                  <small>Send container viewport snapshots to local vision-capable models (e.g. LLaVA, Qwen-VL).</small>
                </div>
              </label>

              <div className="publish-note">
                <Zap size={15} />
                <span>
                  Active Provider Model:{' '}
                  <strong>{config?.providers?.[defaultProvider]?.model || defaultProvider}</strong>
                  {defaultProvider === 'local'
                    ? ' · Zero API cost, loopback only.'
                    : ` · $${config?.providers?.[defaultProvider]?.limits?.input_rate || 3}/M in, $${config?.providers?.[defaultProvider]?.limits?.output_rate || 15}/M out.`}
                </span>
              </div>
            </div>
          )}

          {/* 2. Build Limits Section */}
          {activeSection === 'limits' && (
            <div className="settings-section-pane">
              <div className="limit-grid">
                <label>
                  DEFAULT MAX COST (USD)
                  <input
                    type="number"
                    min={defaultProvider === 'local' ? '0' : '0.10'}
                    max="100"
                    step="0.10"
                    required
                    value={globalBudget}
                    onChange={e => setGlobalBudget(e.target.value)}
                  />
                </label>
                <label>
                  INPUT TOKEN CAP
                  <input
                    type="number"
                    min="10000"
                    max="240000"
                    step="1000"
                    required
                    value={globalMaxInput}
                    onChange={e => setGlobalMaxInput(e.target.value)}
                  />
                </label>
                <label>
                  OUTPUT TOKEN CAP
                  <input
                    type="number"
                    min="1000"
                    max="64000"
                    step="1000"
                    required
                    value={globalMaxOutput}
                    onChange={e => setGlobalMaxOutput(e.target.value)}
                  />
                </label>
              </div>

              <div className="field-group" style={{ marginTop: '16px' }}>
                <label htmlFor="max-repairs-input">MAX AUTO-REPAIR ATTEMPTS</label>
                <input
                  id="max-repairs-input"
                  type="number"
                  min="0"
                  max="5"
                  value={maxRepairs}
                  onChange={e => setMaxRepairs(e.target.value)}
                />
                <small className="field-hint">
                  Number of automatic repair iterations the agent performs upon encountering build/syntax errors.
                </small>
              </div>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={browserChecks}
                  onChange={e => setBrowserChecks(e.target.checked)}
                />
                <div>
                  <strong>Automated Headless Browser Checks</strong>
                  <small>Perform automated browser rendering tests and console error checks after builds.</small>
                </div>
              </label>
            </div>
          )}

          {/* 3. Privacy & Offline Section */}
          {activeSection === 'privacy' && (
            <div className="settings-section-pane">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={offlineOnly}
                  onChange={e => setOfflineOnly(e.target.checked)}
                />
                <div>
                  <strong>Offline-Only Studio Isolation Mode</strong>
                  <small>Block all external network calls and enforce strict offline local model execution.</small>
                </div>
              </label>

              <div className="privacy-card">
                <div className="privacy-card-header">
                  <ShieldCheck size={18} color="#7ae582" />
                  <strong>Strictly Local Architecture</strong>
                </div>
                <p>
                  Local Foundry executes all build containers, compiles source code, and stores databases
                  entirely on your local workstation. Zero source code or user data is telemetried or uploaded
                  to external servers.
                </p>
                <ul className="privacy-checklist">
                  <li><Check size={12} /> Local PostgreSQL database container</li>
                  <li><Check size={12} /> Local Docker sandboxed previews</li>
                  <li><Check size={12} /> Local encrypted recovery packages</li>
                  <li><Check size={12} /> Direct API calls to chosen provider only</li>
                </ul>
              </div>
            </div>
          )}

          {/* 4. Storage & System Section */}
          {activeSection === 'workspace' && (
            <div className="settings-section-pane">
              <div className="field-group">
                <label>GLOBAL DOCUMENTS FOLDER</label>
                <div className="mono-info-box">
                  <Folder size={14} />
                  <span>{config?.documents_folder || '/data/documents'}</span>
                </div>
                <small className="field-hint">Location where local RAG documents are indexed.</small>
              </div>

              <div className="field-group">
                <label>MANAGED FILES FOLDER</label>
                <div className="mono-info-box">
                  <Folder size={14} />
                  <span>{config?.files_folder || '/data/files'}</span>
                </div>
                <small className="field-hint">Folder managed by the Files Agent mode.</small>
              </div>

              <div className="system-specs-grid">
                <div>
                  <span className="spec-lbl">Operating System</span>
                  <span className="spec-val">{config?.runtime?.system} {config?.runtime?.release}</span>
                </div>
                <div>
                  <span className="spec-lbl">Python Runtime</span>
                  <span className="spec-val">Python {config?.runtime?.python || '3.10'}</span>
                </div>
                <div>
                  <span className="spec-lbl">Docker Engine</span>
                  <span className="spec-val">{config?.docker_installed ? 'Installed & Running' : 'Not detected'}</span>
                </div>
                <div>
                  <span className="spec-lbl">Studio Version</span>
                  <span className="spec-val">v{config?.version || '0.10.1'}</span>
                </div>
              </div>

              <div style={{ marginTop: '16px' }}>
                <button
                  type="button"
                  className="secondary wide"
                  onClick={() => {
                    onClose();
                    if (onShowDiagnostics) onShowDiagnostics();
                  }}>
                  <Activity size={14} /> Launch Full System Diagnostics
                </button>
              </div>
            </div>
          )}

          {/* Footer Buttons */}
          <div className="global-settings-footer">
            <button type="button" className="action-btn" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="primary">
              {saved ? <Check size={14} /> : <Settings size={14} />}
              {saved ? 'Saved!' : 'Save Global Settings'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
