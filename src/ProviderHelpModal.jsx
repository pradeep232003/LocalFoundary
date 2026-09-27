import { useState } from 'react';
import {
  Check,
  ChevronRight,
  Copy,
  ExternalLink,
  HardDrive,
  HelpCircle,
  Laptop,
  Server,
  Settings,
  ShieldCheck,
  Terminal,
  X,
  Zap,
} from 'lucide-react';

export default function ProviderHelpModal({
  config,
  currentProvider,
  onOpenSettings,
  onSelectProvider,
  onClose,
}) {
  const [activeTab, setActiveTab] = useState('local');
  const [copiedKey, setCopiedKey] = useState(null);

  function copyText(key, text) {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => {
      setCopiedKey(null);
    }, 2000);
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal provider-help-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="provider-help-title"
        onClick={e => e.stopPropagation()}>
        <button
          type="button"
          className="icon-button modal-close"
          aria-label="Close guide"
          onClick={onClose}>
          <X size={16} />
        </button>

        {/* Header */}
        <div className="provider-help-header">
          <div className="modal-icon help-icon-badge">
            <HelpCircle size={24} />
          </div>
          <div>
            <span className="global-settings-eyebrow">BEGINNER'S TUTORIAL</span>
            <h2 id="provider-help-title">Link Your AI Provider</h2>
          </div>
        </div>

        <p className="global-settings-desc">
          Local Foundry works with local offline AI models or top cloud APIs. Follow these
          simple, step-by-step instructions to get up and running in minutes.
        </p>

        {/* Navigation Tabs */}
        <div className="provider-help-nav" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'local'}
            className={activeTab === 'local' ? 'active' : ''}
            onClick={() => setActiveTab('local')}>
            <Laptop size={15} />
            <span>Local AI (Free)</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'claude'}
            className={activeTab === 'claude' ? 'active' : ''}
            onClick={() => setActiveTab('claude')}>
            <Zap size={15} />
            <span>Claude (Anthropic)</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'openai'}
            className={activeTab === 'openai' ? 'active' : ''}
            onClick={() => setActiveTab('openai')}>
            <Server size={15} />
            <span>OpenAI (GPT-4o)</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'compare'}
            className={activeTab === 'compare' ? 'active' : ''}
            onClick={() => setActiveTab('compare')}>
            <ShieldCheck size={15} />
            <span>At a Glance</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="provider-help-body">
          {/* TAB 1: LOCAL AI */}
          {activeTab === 'local' && (
            <div className="guide-pane">
              <div className="guide-callout success">
                <ShieldCheck size={18} />
                <div>
                  <strong>100% Free, Private & Offline</strong>
                  <p>
                    Local AI runs entirely on your own laptop or desktop. No subscriptions, no
                    credit card, and your code never leaves your computer.
                  </p>
                </div>
              </div>

              <div className="guide-steps">
                {/* Step 1 */}
                <div className="guide-step">
                  <div className="step-num">1</div>
                  <div className="step-content">
                    <h4>Install Ollama</h4>
                    <p>
                      Download and run the free installer for Mac, Windows, or Linux from the official
                      site.
                    </p>
                    <a
                      href="https://ollama.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="guide-link-btn">
                      <span>Visit ollama.com</span>
                      <ExternalLink size={13} />
                    </a>
                  </div>
                </div>

                {/* Step 2 */}
                <div className="guide-step">
                  <div className="step-num">2</div>
                  <div className="step-content">
                    <h4>Download a Coding Model</h4>
                    <p>
                      Open your computer's <strong>Terminal</strong> (Mac/Linux) or{' '}
                      <strong>PowerShell / Command Prompt</strong> (Windows) and paste this command:
                    </p>
                    <div className="code-box">
                      <code>ollama run qwen2.5-coder:7b</code>
                      <button
                        type="button"
                        className="copy-code-btn"
                        onClick={() => copyText('ollama-cmd', 'ollama run qwen2.5-coder:7b')}>
                        {copiedKey === 'ollama-cmd' ? <Check size={13} /> : <Copy size={13} />}
                        <span>{copiedKey === 'ollama-cmd' ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                    <small className="step-hint">
                      💡 Tip: For lighter laptops with limited RAM, you can use{' '}
                      <code>ollama run llama3.2</code> instead.
                    </small>
                  </div>
                </div>

                {/* Step 3 */}
                <div className="guide-step">
                  <div className="step-num">3</div>
                  <div className="step-content">
                    <h4>Connect in Local Foundry</h4>
                    <p>
                      Local Foundry connects to Ollama's local loopback at{' '}
                      <code>http://127.0.0.1:11434/v1</code> automatically.
                    </p>
                    <div className="step-actions">
                      <button
                        type="button"
                        className="guide-action-btn primary-action"
                        onClick={() => {
                          if (onSelectProvider) onSelectProvider('local');
                          onClose();
                        }}>
                        <Zap size={14} /> Switch to Local AI Now
                      </button>
                    </div>
                  </div>
                </div>

                {/* Trouble Shooting Box */}
                <div className="guide-tip-box">
                  <strong>🩺 Quick Connection Check:</strong>
                  <p>
                    To check if Ollama is running, open <code>http://127.0.0.1:11434</code> in your
                    web browser. If you see the message <em>"Ollama is running"</em>, you are ready
                    to build!
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: CLAUDE (ANTHROPIC) */}
          {activeTab === 'claude' && (
            <div className="guide-pane">
              <div className="guide-callout info">
                <Zap size={18} />
                <div>
                  <strong>Gold Standard for Autonomous Coding</strong>
                  <p>
                    Claude (specifically <code>claude-3-7-sonnet</code>) delivers exceptionally
                    clean full-stack code, self-repairs bugs, and follows multi-step architectural
                    instructions with precision.
                  </p>
                </div>
              </div>

              <div className="guide-steps">
                {/* Step 1 */}
                <div className="guide-step">
                  <div className="step-num">1</div>
                  <div className="step-content">
                    <h4>Create an Anthropic Console Account</h4>
                    <p>
                      Sign up for a developer account at the official Anthropic Console.
                    </p>
                    <a
                      href="https://console.anthropic.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="guide-link-btn">
                      <span>Go to console.anthropic.com</span>
                      <ExternalLink size={13} />
                    </a>
                  </div>
                </div>

                {/* Step 2 */}
                <div className="guide-step">
                  <div className="step-num">2</div>
                  <div className="step-content">
                    <h4>Generate an API Key</h4>
                    <p>
                      In the console, click on <strong>API Keys</strong> in the left sidebar, then
                      click <strong>"Create Key"</strong>. Copy your new secret key (it begins with{' '}
                      <code>sk-ant-api03-...</code>).
                    </p>
                  </div>
                </div>

                {/* Step 3 */}
                <div className="guide-step">
                  <div className="step-num">3</div>
                  <div className="step-content">
                    <h4>Add to Local Foundry</h4>
                    <p>
                      Open your project's <strong>App Settings</strong> tab and add your key to the
                      Environment Variables, or add it to your <code>.env</code> file:
                    </p>
                    <div className="code-box">
                      <code>ANTHROPIC_API_KEY=sk-ant-api03-YOUR_KEY_HERE</code>
                      <button
                        type="button"
                        className="copy-code-btn"
                        onClick={() =>
                          copyText(
                            'claude-env',
                            'ANTHROPIC_API_KEY=sk-ant-api03-YOUR_KEY_HERE'
                          )
                        }>
                        {copiedKey === 'claude-env' ? <Check size={13} /> : <Copy size={13} />}
                        <span>{copiedKey === 'claude-env' ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Pricing Guide */}
                <div className="guide-tip-box">
                  <strong>💵 What does it cost?</strong>
                  <p>
                    Anthropic charges strictly per token used. A typical build or revision costs
                    approximately <strong>$0.02 – $0.05</strong>. You can cap total expenditure in
                    the <em>Build Limits</em> settings modal at any time.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: OPENAI */}
          {activeTab === 'openai' && (
            <div className="guide-pane">
              <div className="guide-callout info">
                <Server size={18} />
                <div>
                  <strong>Fast, Industry-Proven Intelligence (GPT-4o)</strong>
                  <p>
                    OpenAI provides the famous GPT-4o model, known for swift response times, strong
                    reasoning capabilities, and reliable API availability.
                  </p>
                </div>
              </div>

              <div className="guide-steps">
                {/* Step 1 */}
                <div className="guide-step">
                  <div className="step-num">1</div>
                  <div className="step-content">
                    <h4>Sign Up on the OpenAI Developer Platform</h4>
                    <p>
                      Log in to the developer portal (note: this is separate from the personal
                      ChatGPT subscription).
                    </p>
                    <a
                      href="https://platform.openai.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="guide-link-btn">
                      <span>Go to platform.openai.com</span>
                      <ExternalLink size={13} />
                    </a>
                  </div>
                </div>

                {/* Step 2 */}
                <div className="guide-step">
                  <div className="step-num">2</div>
                  <div className="step-content">
                    <h4>Add Starter Credit Balance</h4>
                    <p>
                      In <strong>Settings → Billing</strong>, add a pre-paid balance (minimum $5) to
                      activate API access.
                    </p>
                  </div>
                </div>

                {/* Step 3 */}
                <div className="guide-step">
                  <div className="step-num">3</div>
                  <div className="step-content">
                    <h4>Create an API Key</h4>
                    <p>
                      Go to <strong>Dashboard → API Keys</strong>, click{' '}
                      <strong>"Create new secret key"</strong>, and copy the string (starts with{' '}
                      <code>sk-proj-...</code>).
                    </p>
                    <div className="code-box">
                      <code>OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE</code>
                      <button
                        type="button"
                        className="copy-code-btn"
                        onClick={() =>
                          copyText('openai-env', 'OPENAI_API_KEY=sk-proj-YOUR_KEY_HERE')
                        }>
                        {copiedKey === 'openai-env' ? <Check size={13} /> : <Copy size={13} />}
                        <span>{copiedKey === 'openai-env' ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>
                  </div>
                </div>

                <div className="guide-tip-box">
                  <strong>💡 Pro-Tip:</strong>
                  <p>
                    After adding your key, select <strong>OpenAI</strong> in the AI Model dropdown
                    or Global Settings to start generating applications with GPT-4o.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: AT A GLANCE COMPARISON */}
          {activeTab === 'compare' && (
            <div className="guide-pane">
              <div className="comparison-table-wrapper">
                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th>Provider</th>
                      <th>Cost</th>
                      <th>Privacy</th>
                      <th>Best Used For</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>
                        <strong>Local AI</strong>
                        <small>Ollama / vLLM</small>
                      </td>
                      <td>
                        <span className="badge-tag free">100% Free</span>
                      </td>
                      <td>
                        <span className="badge-tag safe">100% Offline</span>
                      </td>
                      <td>Private projects, zero-cost tinkering, confidential codebases.</td>
                    </tr>
                    <tr>
                      <td>
                        <strong>Claude</strong>
                        <small>Anthropic 3.7 Sonnet</small>
                      </td>
                      <td>
                        <span className="badge-tag paid">~$0.03 / build</span>
                      </td>
                      <td>Cloud (Anthropic)</td>
                      <td>Complex full-stack apps, autonomous bug self-healing, React design.</td>
                    </tr>
                    <tr>
                      <td>
                        <strong>OpenAI</strong>
                        <small>GPT-4o</small>
                      </td>
                      <td>
                        <span className="badge-tag paid">~$0.02 / build</span>
                      </td>
                      <td>Cloud (OpenAI)</td>
                      <td>Fast iteration, general scripts, rapid prototyping.</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div className="guide-tip-box" style={{ marginTop: '16px' }}>
                <strong>🔄 You Can Switch Anytime:</strong>
                <p>
                  You are never locked into one provider! Switch between Local AI for free offline
                  experimentation and Claude/OpenAI for heavier builds whenever you choose.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="global-settings-footer">
          <button type="button" className="action-btn" onClick={onClose}>
            Close Guide
          </button>
          <button
            type="button"
            className="primary"
            onClick={() => {
              onClose();
              if (onOpenSettings) onOpenSettings();
            }}>
            <Settings size={14} /> Open Global Settings
          </button>
        </div>
      </div>
    </div>
  );
}
