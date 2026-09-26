import { useEffect, useRef, useState } from 'react';
import {
  Activity,
  Archive,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleDollarSign,
  Code2,
  Database,
  Download,
  FileCode2,
  Files,
  Folder,
  Github,
  HardDrive,
  History,
  Loader2,
  Monitor,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Camera,
  Package,
  Rocket,
  Settings,
  SlidersHorizontal,
  Smartphone,
  ShieldCheck,
  Square,
  Terminal,
  Upload,
  Wand2,
  WifiOff,
  X,
  Zap,
} from 'lucide-react';
import { request, download, downloadRecovery, importRecovery } from './api';
import BuildTools, { BuildOptions } from './BuildTools';
import DocumentsPanel from './panels/DocumentsPanel';
import FilesPanel from './panels/FilesPanel';
import RecoveryPanel from './panels/RecoveryPanel';
import MobilePanel from './panels/MobilePanel';
import SettingsPanel from './panels/SettingsPanel';
import GlobalSettingsModal from './GlobalSettingsModal';
import { date } from './format';
import ProjectContinuity from './ProjectContinuity';

const examples = [
  [
    'A personal reading list',
    'Build a reading list with books, authors, reading status, and a clean filterable grid. Persist everything in PostgreSQL.',
  ],
  [
    'A client project tracker',
    'Build a project tracker with clients, project status, deadlines, and a calm dashboard. Store projects in PostgreSQL.',
  ],
  [
    'An everyday habit journal',
    'Build a habit journal with daily check-ins, a weekly overview, and progress cards. Use PostgreSQL for persistence.',
  ],
];

export default function App() {
  const [config, setConfig] = useState(null);
  const [projects, setProjects] = useState([]);
  const [id, setId] = useState(null);
  const [project, setProject] = useState(null);
  const [provider, setProvider] = useState('anthropic');
  const [mode, setMode] = useState('coder');
  const [prompt, setPrompt] = useState('');
  const [tab, setTab] = useState('preview');
  const [showSidebar, setShowSidebar] = useState(true);
  const [showPreviewPanel, setShowPreviewPanel] = useState(true);
  const [showPreviewMenu, setShowPreviewMenu] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [run, setRun] = useState(null);
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [modal, setModal] = useState(null);
  const [name, setName] = useState('');
  const [profile, setProfile] = useState('accounts');
  const [repoName, setRepoName] = useState('');
  const [commitMessage, setCommitMessage] = useState('Save app from Local Foundry');
  const [githubReview, setGithubReview] = useState(null);
  const [budget, setBudget] = useState('2.00');
  const [maxInput, setMaxInput] = useState('180000');
  const [maxOutput, setMaxOutput] = useState('24000');
  const [buildOptions, setBuildOptions] = useState({
    max_repairs: 2,
    browser_checks: true,
    share_screenshots: false,
  });
  const [documentQuery, setDocumentQuery] = useState('');
  const [documentResults, setDocumentResults] = useState([]);
  const [recoveryPassword, setRecoveryPassword] = useState('');
  const [recoveryConfirm, setRecoveryConfirm] = useState('');
  const [recoveryName, setRecoveryName] = useState('');
  const [recoveryFile, setRecoveryFile] = useState(null);
  const [diagnostics, setDiagnostics] = useState(null);
  const [paths, setPaths] = useState([]);
  const [selectedPath, setSelectedPath] = useState('');
  const [source, setSource] = useState('');
  const [logs, setLogs] = useState('');
  const [previewKey, setPreviewKey] = useState(0);
  const [showLive, setShowLive] = useState(false);
  const end = useRef(null);
  const selectedId = useRef(null);
  const fileRequest = useRef(0);
  const tabListRef = useRef(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateScrollIndicators = () => {
    const el = tabListRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 4);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 4);
  };

  useEffect(() => {
    updateScrollIndicators();
    window.addEventListener('resize', updateScrollIndicators);
    return () => window.removeEventListener('resize', updateScrollIndicators);
  }, [project?.id, tab]);

  useEffect(() => {
    const activeEl = tabListRef.current?.querySelector(`button[aria-selected="true"]`);
    if (activeEl) {
      activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }
  }, [tab]);

  const scrollTabs = (direction) => {
    if (tabListRef.current) {
      tabListRef.current.scrollBy({ left: direction * 180, behavior: 'smooth' });
      setTimeout(updateScrollIndicators, 300);
    }
  };

  const handleTabsWheel = (e) => {
    if (tabListRef.current && e.deltaY !== 0) {
      e.preventDefault();
      tabListRef.current.scrollLeft += e.deltaY;
      updateScrollIndicators();
    }
  };

  async function refreshList() {
    const p = await request('/projects');
    setProjects(p);
    return p;
  }
  async function refreshProject(projectId) {
    const data = await request(`/projects/${projectId}`);
    if (selectedId.current === projectId) setProject(data);
    return data;
  }
  useEffect(() => {
    Promise.all([request('/config'), refreshList()])
      .then(([c, p]) => {
        setConfig(c);
        if (
          c.offline_only ||
          (!c.providers.anthropic.configured &&
            !c.providers.openai.configured &&
            c.providers.local.configured)
        )
          setProvider('local');
        else if (!c.providers.anthropic.configured && c.providers.openai.configured) setProvider('openai');
        if (p.length) setId(p[0].id);
      })
      .catch(e => setError(e.message));
  }, []);
  useEffect(() => {
    selectedId.current = id;
    fileRequest.current += 1;
    setProject(null);
    setRun(null);
    setEvents([]);
    setSource('');
    setSelectedPath('');
    setPaths([]);
    setLogs('');
    setDocumentResults([]);
    setError('');
    if (!id) return;
    refreshProject(id)
      .then(p => {
        if (selectedId.current === id && p.active_run)
          setRun({ id: p.active_run, kind: p.active_run_kind, status: 'running' });
      })
      .catch(e => setError(e.message));
  }, [id]);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length, project?.messages?.length]);
  useEffect(() => {
    if (!run || run.status !== 'running') return;
    let stopped = false,
      after = 0,
      timer;
    async function poll() {
      try {
        const data = await request(`/runs/${run.id}?after=${after}`);
        if (stopped) return;
        if (data.events.length) {
          after = data.events.at(-1).id;
          setEvents(old => [...old, ...data.events]);
        }
        if (data.status !== 'running' && !data.more) {
          setRun({ ...run, status: data.status });
          setBusy(false);
          if (['failed', 'budget_exceeded'].includes(data.status))
            setError(
              data.events.findLast(e => e.kind === 'error')?.text ||
                'Operation stopped. Open Activity for details.',
            );
          if (data.status === 'awaiting_approval') {
            setNotice('Build paused. Review the requested dependencies in Packages.');
            setTab('packages');
          }
          if (data.status === 'awaiting_plan') {
            setNotice('Feature plan saved. Review it in Roadmap.');
            setTab('roadmap');
          }
          if (data.status === 'completed')
            setNotice(
              run.kind === 'build'
                ? 'Build completed and every required check passed.'
                : run.kind === 'documents'
                  ? 'Document research completed.'
                  : run.kind === 'files'
                    ? 'File plan created; review it before applying.'
                    : run.kind === 'validation'
                      ? 'Every required check passed.'
                      : run.kind === 'backup'
                        ? 'Database backup created.'
                        : run.kind === 'backup_restore'
                          ? 'Database restored; a safeguard backup was kept.'
                          : run.kind === 'recovery'
                            ? 'Encrypted recovery archive created.'
                            : 'Operation completed.',
            );
          await refreshProject(id);
          await refreshList();
          setPreviewKey(k => k + 1);
          return;
        }
      } catch (e) {
        if (!stopped) setError(e.message);
      }
      if (!stopped) timer = setTimeout(poll, 1300);
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [run?.id, run?.status, id]);
  useEffect(() => {
    if (!id) return;
    let valid = true;
    if (tab === 'code')
      request(`/projects/${id}/files`)
        .then(p => {
          if (valid) {
            const list = Array.isArray(p)
              ? p.map(item => (typeof item === 'string' ? item : item.path))
              : [];
            setPaths(list);
            if (list.length > 0 && !selectedPath) {
              readFile(list[0]);
            }
          }
        })
        .catch(e => setError(e.message));
    if (tab === 'logs') loadLogs();
    return () => {
      valid = false;
    };
  }, [tab, id, run?.status]);

  const running = busy || run?.status === 'running';
  const configured = config?.providers?.[provider]?.configured;
  const pricingKnown = config?.providers?.[provider]?.limits?.pricing_known;
  const providerReady = configured && pricingKnown;
  const currentEvent = events
    .filter(e =>
      ['status', 'tool', 'check', 'retry', 'usage', 'repair', 'approval', 'visual_review'].includes(e.kind),
    )
    .at(-1);
  const cancellable =
    run?.status === 'running' &&
    [
      'build',
      'milestones',
      'documents',
      'files',
      'validation',
      'mobile_apk',
      'mobile_aab',
      'mobile_ipa',
    ].includes(run?.kind);

  async function perform(fn) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function launch(path, body = {}) {
    const data = await request(path, body);
    setEvents([]);
    setRun({ id: data.run_id, kind: data.kind, status: 'running' });
    setShowLive(true);
  }
  async function create(e) {
    e.preventDefault();
    perform(async () => {
      const p = await request('/projects', { name, profile });
      await refreshList();
      setId(p.id);
      setModal(null);
      setName('');
    });
  }
  async function build(e) {
    e.preventDefault();
    if (!prompt.trim() || !project) return;
    const cost = Number(budget),
      input = Number(maxInput),
      output = Number(maxOutput);
    if (
      ![cost, input, output].every(Number.isFinite) ||
      !Number.isInteger(input) ||
      !Number.isInteger(output) ||
      cost < 0 ||
      (provider !== 'local' && cost < 0.1) ||
      cost > 100 ||
      input < 10000 ||
      input > 240000 ||
      output < 1000 ||
      output > 64000
    ) {
      setError('Choose valid build limits before sending.');
      setModal('budget');
      return;
    }
    perform(async () => {
      await launch(`/projects/${id}/build`, {
        prompt,
        provider,
        mode,
        budget_usd: cost,
        max_input_tokens: input,
        max_output_tokens: output,
        ...buildOptions,
        share_screenshots: buildOptions.share_screenshots && (provider !== 'local' || config.local_vision),
      });
      setPrompt('');
      await refreshProject(id);
    });
  }
  async function readFile(path) {
    if (!path) return;
    const filePath = typeof path === 'string' ? path : path?.path || '';
    const serial = ++fileRequest.current;
    setSelectedPath(filePath);
    setSource('Loading…');
    try {
      const data = await request(`/projects/${id}/file?path=${encodeURIComponent(filePath)}`);
      if (serial === fileRequest.current) setSource(data.content);
    } catch (e) {
      setError(e.message);
    }
  }
  async function loadLogs() {
    const projectId = id;
    try {
      const data = await request(`/projects/${id}/logs`);
      if (selectedId.current === projectId) setLogs(data.text || 'No logs yet. Start the preview first.');
    } catch (e) {
      if (selectedId.current === projectId) setLogs(e.message);
    }
  }
  function openGithub() {
    setRepoName(
      project.repo?.split('/')[1] ||
        project.name
          .toLowerCase()
          .replace(/[^a-z0-9-]/g, '-')
          .replace(/^-+|-+$/g, '') ||
        'my-app',
    );
    setGithubReview(null);
    setError('');
    setModal('github');
  }
  async function reviewGithub(e) {
    e.preventDefault();
    await perform(async () =>
      setGithubReview(await request(`/projects/${id}/github/review`, { name: repoName })),
    );
  }
  async function publishGithub() {
    if (!githubReview || githubReview.conflicts.length) return;
    await perform(async () => {
      await launch(`/projects/${id}/github`, {
        name: repoName,
        message: commitMessage,
        expected_head: githubReview.head,
        source_digest: githubReview.source_digest,
      });
      setModal(null);
      setGithubReview(null);
    });
  }
  async function searchDocuments(e) {
    e?.preventDefault();
    if (!documentQuery.trim()) return;
    await perform(async () => {
      const data = await request(
        `/projects/${id}/documents/search?q=${encodeURIComponent(documentQuery.trim())}`,
      );
      setDocumentResults(data.results);
    });
  }
  async function showDiagnostics() {
    await perform(async () => {
      setDiagnostics(await request('/diagnostics'));
      setModal('diagnostics');
    });
  }
  function closeModal() {
    setModal(null);
    setRecoveryPassword('');
    setRecoveryConfirm('');
    setRecoveryName('');
    setRecoveryFile(null);
  }
  function openRecoveryImport() {
    setRecoveryPassword('');
    setRecoveryConfirm('');
    setRecoveryName('');
    setRecoveryFile(null);
    setModal('import');
  }
  async function doImportRecovery(e) {
    e.preventDefault();
    if (!recoveryFile || recoveryPassword.length < 12 || recoveryPassword !== recoveryConfirm) return;
    await perform(async () => {
      const imported = await importRecovery(recoveryFile, recoveryPassword, recoveryName);
      await refreshList();
      setId(imported.id);
      closeModal();
    });
  }

  return (
    <div className="app">
      <aside className={`sidebar ${!showSidebar ? 'hidden' : ''}`}>
        <div className="brand-header">
          <a className="brand" href="/" aria-label="Local Foundry home">
            <span className="brand-mark">
              <Code2 size={20} />
            </span>
            <span>
              local<span className="muted">foundry</span>
              <small>YOUR PERSONAL APP STUDIO</small>
            </span>
          </a>
          <button
            type="button"
            className="sidebar-arrow-btn"
            title="Hide Side menu"
            aria-label="Hide Side menu"
            onClick={() => setShowSidebar(false)}>
            <ChevronLeft size={16} />
          </button>
        </div>
        <button className="new-project" onClick={() => setModal('new')}>
          <Plus size={17} /> New project <span>⌘</span>
        </button>
        <div className="section-label">
          WORKSPACE <span>{projects.length.toString().padStart(2, '0')}</span>
        </div>
        <nav aria-label="Projects">
          {projects.map(p => (
            <button
              key={p.id}
              // Narrow widths hide the label span, which would otherwise leave a
              // button of decorative icons with no accessible name at all.
              aria-label={p.name}
              aria-current={id === p.id ? 'true' : undefined}
              className={'project-link ' + (id === p.id ? 'selected' : '')}
              onClick={() => setId(p.id)}>
              <Folder size={16} />
              <span>{p.name}</span>
              {p.repo && <Github size={12} />}
            </button>
          ))}
        </nav>
        {!projects.length && (
          <p className="sidebar-empty">
            A place for your next idea.
            <br />
            Create a project to begin.
          </p>
        )}
        <div className="sidebar-bottom">
          <div className="local-badge">
            <span className="status-dot" /> Running locally
          </div>
          <p>
            Your code stays on your computer.
            <br />
            AI requests use your selected provider.
          </p>
          <div className="profile">
            <span>LF</span>
            <div>
              Personal workspace<small>{config?.runtime?.label || 'Local'} · Docker previews</small>
            </div>
          </div>
        </div>
      </aside>

      {/* Button on the line to hide / show Side Menu */}
      <div
        className={`sidebar-divider-line ${!showSidebar ? 'collapsed' : ''}`}
        title={showSidebar ? 'Click to hide Side Menu' : 'Click to show Side Menu'}>
        <button
          type="button"
          className="line-toggle-btn side-line-btn"
          aria-label={showSidebar ? 'Click to hide Side Menu' : 'Click to show Side Menu'}
          title={showSidebar ? 'Click to hide Side Menu' : 'Click to show Side Menu'}
          onClick={() => setShowSidebar(v => !v)}>
          {showSidebar ? <ChevronLeft size={13} /> : <ChevronRight size={13} />}
        </button>
      </div>

      <main className="main">
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className={`icon-button side-toggle-btn ${!showSidebar ? 'sidebar-hidden' : ''}`}
              aria-label={showSidebar ? 'Hide Side menu' : 'Show Side menu'}
              title={showSidebar ? 'Hide Side menu' : 'Show Side menu'}
              onClick={() => setShowSidebar(v => !v)}>
              {showSidebar ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
              <span className="toggle-label">{showSidebar ? 'Hide Side Menu' : 'Side Menu'}</span>
            </button>
            <div className="breadcrumb">
              Workspace <span>/</span> <strong>{project?.name || 'Overview'}</strong>
            </div>
          </div>
          <div className="header-actions">
            {config?.offline_only && (
              <span className="offline-label">
                <WifiOff size={13} /> Offline only
              </span>
            )}
            {project?.last_validation?.status === 'passed' && (
              <span className="verified-label">
                <Check size={13} /> Checks passed
              </span>
            )}
            <button
              className={`icon-button ${modal === 'global-settings' ? 'active' : ''}`}
              aria-label="Local Foundry Global Settings"
              title="Local Foundry Global Settings"
              onClick={() => setModal('global-settings')}>
              <Settings size={17} />
            </button>
            <button className="icon-button" aria-label="System diagnostics" onClick={showDiagnostics}>
              <Activity size={17} />
            </button>
            <span className="private-label">
              <ShieldCheck size={14} /> Local workspace
            </span>
            {project && (
              <>
                <button
                  className="icon-button"
                  aria-label="Download source code"
                  disabled={running}
                  onClick={() => perform(() => download(project))}>
                  <Download size={17} />
                </button>
                <button
                  className="github-button"
                  disabled={running || config?.offline_only}
                  onClick={openGithub}>
                  <Github size={15} /> Save to GitHub
                </button>
              </>
            )}
          </div>
        </header>
        {error && (
          <div className="banner error" role="alert">
            <span>{error}</span>
            <button aria-label="Dismiss error" onClick={() => setError('')}>
              <X size={15} />
            </button>
          </div>
        )}
        {notice && !error && (
          <div className="banner success" role="status">
            <span>
              <Check size={14} /> {notice}
            </span>
            <button aria-label="Dismiss notification" onClick={() => setNotice('')}>
              <X size={15} />
            </button>
          </div>
        )}
        {!project ? (
          <div className="welcome">
            <div className="welcome-icon">
              <Wand2 size={30} />
            </div>
            <div className="eyebrow">FROM IDEA TO YOUR OWN APP</div>
            <h1>
              Your ideas.
              <br />
              <span>Your workspace.</span>
            </h1>
            <p>
              Build with AI. Search local documents. Organize files safely.
              <br />
              Preview on your computer and keep every line of code.
            </p>
            <div className="welcome-actions">
              <button className="primary" onClick={() => setModal('new')}>
                <Plus size={17} /> Create your first project
              </button>
              <button className="secondary" onClick={openRecoveryImport}>
                <Upload size={16} /> Import recovery
              </button>
            </div>
            <div className="stack-chips">
              <span>React</span>
              <span>Python</span>
              <span>PostgreSQL</span>
              <span>Local AI</span>
            </div>
            <div className="idea-cards">
              {examples.map(([title, text]) => (
                <button
                  key={title}
                  onClick={() => {
                    setPrompt(text);
                    setName(title);
                    setModal('new');
                  }}>
                  <Folder size={19} />
                  <span>{title}</span>
                  <ArrowUpRight size={15} />
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="workbench">
            <section className={`chat-panel ${!showPreviewPanel ? 'full-width' : ''}`} aria-label="AI conversation">
              <div className="panel-title">
                <span>
                  <Wand2 size={16} /> Build together
                </span>
                <div className="panel-title-actions">
                  <button
                    type="button"
                    className="toggle-preview-panel-badge-btn"
                    title={showPreviewPanel ? 'Click to hide Preview panel' : 'Click to show Preview panel'}
                    aria-label={showPreviewPanel ? 'Click to hide Preview panel' : 'Click to show Preview panel'}
                    onClick={() => setShowPreviewPanel(v => !v)}>
                    {showPreviewPanel ? (
                      <>
                        <span>Hide Preview</span>
                        <ChevronRight size={13} />
                      </>
                    ) : (
                      <>
                        <ChevronLeft size={13} />
                        <span>Show Preview</span>
                      </>
                    )}
                  </button>
                  <span className="tiny-label">AI ASSISTANT</span>
                </div>
              </div>
              <div className="conversation">
                <div className="assistant-intro">
                  <span className="assistant-icon">
                    <Zap size={17} />
                  </span>
                  <div>
                    <strong>What are we making?</strong>
                    <p>
                      Your project is ready. Describe what you want to build, or start the preview to explore
                      the working template.
                    </p>
                  </div>
                </div>
                {!project.messages.length && (
                  <div className="chat-suggestions">
                    {examples.map(([title, text]) => (
                      <button key={title} onClick={() => setPrompt(text)}>
                        {title}
                        <ArrowUpRight size={13} />
                      </button>
                    ))}
                  </div>
                )}
                {project.messages.map((m, i) => (
                  <div className={'message ' + m.role} key={i}>
                    <div className="message-label">
                      {m.role === 'user'
                        ? `YOU · ${(m.mode || 'coder').toUpperCase()}`
                        : `FOUNDRY · ${(m.mode || 'coder').toUpperCase()}`}
                    </div>
                    <div>{m.content}</div>
                  </div>
                ))}
                {events.length > 0 && (
                  <div className="activity">
                    <button className="activity-toggle" onClick={() => setShowLive(v => !v)}>
                      {run?.status === 'running' ? (
                        <Loader2 size={14} className="spin" />
                      ) : (
                        <Terminal size={14} />
                      )}
                      <span>
                        {run?.status === 'running'
                          ? currentEvent?.text || 'Working…'
                          : `Activity · ${run?.status}`}
                      </span>
                      <ChevronDown size={14} />
                    </button>
                    {showLive && (
                      <div className="event-list">
                        {events.map(e => (
                          <div className={'event ' + e.kind} key={e.id}>
                            <span>
                              {['error', 'tool_error'].includes(e.kind)
                                ? '!'
                                : e.kind === 'check' && e.status === 'passed'
                                  ? '✓'
                                  : '›'}
                            </span>
                            <div>
                              {e.text}
                              {e.url && (
                                <a href={e.url} target="_blank" rel="noreferrer">
                                  Open <ArrowUpRight size={12} />
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <div ref={end} />
              </div>
              <form className="composer" onSubmit={build}>
                <textarea
                  aria-label="Describe your app or change"
                  placeholder={
                    mode === 'coder'
                      ? 'Describe your app, or ask for a change…'
                      : mode === 'documents'
                        ? 'Ask a question about indexed local documents…'
                        : 'Describe how to organize the managed files folder…'
                  }
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  maxLength={12000}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) build(e);
                  }}
                />
                <div className="composer-bottom">
                  <div className="composer-options">
                    <div
                      className="model-picker"
                      title="Select agent role (Coder, Documents, Files)"
                      onClick={e => {
                        const sel = e.currentTarget.querySelector('select');
                        if (sel && typeof sel.showPicker === 'function') {
                          try { sel.showPicker(); } catch {}
                        }
                      }}>
                      <Wand2 size={13} />
                      <span className="picker-text">
                        {mode === 'coder' ? 'Coder' : mode === 'documents' ? 'Documents' : 'Files'}
                      </span>
                      <ChevronDown size={12} className="picker-arrow" />
                      <select
                        aria-label="Agent role"
                        value={mode}
                        onChange={e => setMode(e.target.value)}
                        disabled={running}>
                        <option value="coder">Coder</option>
                        <option value="documents">Documents</option>
                        <option value="files">Files</option>
                      </select>
                    </div>

                    <div
                      className="model-picker"
                      title="Select AI model provider (Claude, OpenAI, Local AI)"
                      onClick={e => {
                        const sel = e.currentTarget.querySelector('select');
                        if (sel && typeof sel.showPicker === 'function') {
                          try { sel.showPicker(); } catch {}
                        }
                      }}>
                      <Zap size={13} />
                      <span className="picker-text">
                        {provider === 'anthropic' ? 'Claude' : provider === 'openai' ? 'OpenAI' : 'Local AI'}
                      </span>
                      <ChevronDown size={12} className="picker-arrow" />
                      <select
                        aria-label="AI provider"
                        value={provider}
                        onChange={e => setProvider(e.target.value)}
                        disabled={running}>
                        <option value="anthropic">Claude</option>
                        <option value="openai">OpenAI</option>
                        <option value="local">Local AI</option>
                      </select>
                    </div>

                    <div
                      className="model-picker prompt-ideas-picker"
                      title="Quick prompt templates and ideas"
                      onClick={e => {
                        const sel = e.currentTarget.querySelector('select');
                        if (sel && typeof sel.showPicker === 'function') {
                          try { sel.showPicker(); } catch {}
                        }
                      }}>
                      <span className="picker-text">💡 Ideas</span>
                      <ChevronDown size={12} className="picker-arrow" />
                      <select
                        aria-label="Quick prompt suggestions"
                        value=""
                        onChange={e => {
                          if (e.target.value) setPrompt(e.target.value);
                        }}
                        disabled={running}>
                        <option value="" disabled>💡 Choose a change or prompt idea…</option>
                        <option value="Add categories and tag filtering with colored badges">
                          🏷️ Add categories & filter tags
                        </option>
                        <option value="Add weekly completion progress bar and monthly statistics view">
                          📊 Add weekly stats & charts
                        </option>
                        <option value="Add daily reminder notification times and sound alert settings">
                          🔔 Add reminder notifications
                        </option>
                        <option value="Add export to CSV and JSON backup download options">
                          💾 Export data to CSV & JSON
                        </option>
                        <option value="Add dark and light theme toggle with smooth animation">
                          🌓 Dark / Light theme toggle
                        </option>
                        <option value="Refactor responsive layout for small mobile screens and eliminate horizontal overflow">
                          📱 Mobile responsive layout check
                        </option>
                      </select>
                    </div>

                    <button
                      type="button"
                      className="budget-button"
                      onClick={() => setModal('budget')}
                      disabled={running}
                      aria-label="Set build budget">
                      <CircleDollarSign size={13} />
                      {provider === 'local' ? 'Local' : `$${Number(budget || 0).toFixed(2)}`}
                    </button>
                  </div>
                  <button
                    className="send-button"
                    aria-label="Run agent"
                    disabled={running || !prompt.trim() || !providerReady}>
                    <ArrowUp size={18} />
                  </button>
                </div>
              </form>
              <div className="composer-foot">
                {running ? (
                  cancellable ? (
                    <button
                      onClick={() =>
                        perform(async () => {
                          const r = await request(`/runs/${run.id}/cancel`, {});
                          setNotice(r.message);
                        })
                      }
                      disabled={!run || busy}>
                      Stop {run.kind === 'validation' ? 'validation' : 'agent'}
                    </button>
                  ) : (
                    <span>{currentEvent?.text || 'Operation in progress…'}</span>
                  )
                ) : !configured ? (
                  <span>
                    {provider === 'local'
                      ? 'Set LOCAL_MODEL and start your loopback model server.'
                      : `Add your ${provider === 'anthropic' ? 'Anthropic' : 'OpenAI'} API key to .env, then restart.`}
                  </span>
                ) : !pricingKnown ? (
                  <span>Add custom-model token rates to .env, then restart.</span>
                ) : (
                  <span>
                    {config.providers[provider].model} ·{' '}
                    {provider === 'local'
                      ? 'loopback only · no API cost'
                      : `$${config.providers[provider].limits.input_rate}/M in · $${config.providers[provider].limits.output_rate}/M out`}
                  </span>
                )}
              </div>
              <div className="build-settings-bar">
                <button disabled={running} onClick={() => setModal('build-options')}>
                  <SlidersHorizontal size={13} /> Build controls
                </button>
                <span>
                  {buildOptions.max_repairs} repairs · browser checks{' '}
                  {buildOptions.browser_checks ? 'on' : 'off'}
                </span>
              </div>
            </section>

            {/* Button on the line to hide / show Preview Panel */}
            <div
              className={`workbench-divider-line ${!showPreviewPanel ? 'collapsed' : ''}`}
              title={showPreviewPanel ? 'Click to hide Preview panel' : 'Click to show Preview panel'}>
              <button
                type="button"
                className="line-toggle-btn preview-line-btn"
                aria-label={showPreviewPanel ? 'Click to hide Preview panel' : 'Click to show Preview panel'}
                title={showPreviewPanel ? 'Click to hide Preview panel' : 'Click to show Preview panel'}
                onClick={() => setShowPreviewPanel(v => !v)}>
                {showPreviewPanel ? <ChevronRight size={13} /> : <ChevronLeft size={13} />}
              </button>
            </div>

            <section
              className={`preview-panel ${!showPreviewPanel ? 'hidden' : ''}`}
              aria-label="Project workspace">
              {showPreviewMenu ? (
                <div className="preview-tabs">
                  <div className="tabs-nav-container">
                    {canScrollLeft && (
                      <button
                        type="button"
                        className="tab-scroll-btn left"
                        aria-label="Scroll tabs left"
                        title="Scroll tabs left"
                        onClick={() => scrollTabs(-1)}>
                        <ChevronLeft size={14} />
                      </button>
                    )}
                    <div
                      ref={tabListRef}
                      role="tablist"
                      aria-label="Project views"
                      className="tabs-scroll-area"
                      onWheel={handleTabsWheel}
                      onScroll={updateScrollIndicators}>
                      {[
                        ['preview', Monitor, 'Preview'],
                        ['roadmap', Wand2, 'Roadmap'],
                        ['context', BookOpen, 'Context'],
                        ['settings', Settings, 'App Settings'],
                        ['visual', Camera, 'Visual'],
                        ['code', Code2, 'Code'],
                        ['packages', Package, 'Packages'],
                        ['release', Rocket, 'Release'],
                        ['mobile', Smartphone, 'Mobile'],
                        ['logs', Terminal, 'Logs'],
                        ['versions', History, 'Versions'],
                        ['data', Database, 'Data'],
                        ['documents', BookOpen, 'Docs'],
                        ['files', Files, 'Files'],
                        ['recovery', Archive, 'Recovery'],
                      ].map(([key, Icon, label]) => (
                        <button
                          role="tab"
                          title={label}
                          aria-label={label}
                          aria-selected={tab === key}
                          key={key}
                          className={tab === key ? 'active' : ''}
                          onClick={() => setTab(key)}>
                          <Icon size={14} />
                          <span>{label}</span>
                        </button>
                      ))}
                    </div>
                    {canScrollRight && (
                      <button
                        type="button"
                        className="tab-scroll-btn right"
                        aria-label="Scroll tabs right"
                        title="Scroll tabs right"
                        onClick={() => scrollTabs(1)}>
                        <ChevronRight size={14} />
                      </button>
                    )}
                  </div>
                  <div className="preview-tabs-right">
                    <span className="sandbox-label">
                      <ShieldCheck size={13} /> {tab === 'mobile' ? 'Native tools' : 'Sandbox'}
                    </span>
                    <button
                      type="button"
                      className="preview-menu-toggle-btn"
                      aria-label="Hide Preview Menu"
                      title="Hide Preview Menu"
                      onClick={() => setShowPreviewMenu(false)}>
                      <ChevronUp size={14} />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="preview-menu-minibar">
                  <button
                    type="button"
                    className="preview-menu-expand-btn"
                    aria-label="Show Preview Menu"
                    title="Show Preview Menu"
                    onClick={() => setShowPreviewMenu(true)}>
                    <ChevronDown size={14} />
                    <span>Show Preview Menu (Current view: <strong>{tab}</strong>)</span>
                  </button>
                  <div className="preview-tabs-right">
                    <span className="sandbox-label">
                      <ShieldCheck size={13} /> {tab === 'mobile' ? 'Native tools' : 'Sandbox'}
                    </span>
                    <button
                      type="button"
                      className="preview-menu-toggle-btn"
                      aria-label="Show Preview Menu"
                      title="Show Preview Menu"
                      onClick={() => setShowPreviewMenu(true)}>
                      <ChevronDown size={14} />
                    </button>
                  </div>
                </div>
              )}
              {['context', 'roadmap'].includes(tab) && (
                <ProjectContinuity
                  tab={tab}
                  project={project}
                  running={running}
                  perform={perform}
                  launch={launch}
                  refresh={() => refreshProject(id)}
                  providerReady={providerReady}
                  buildSettings={{
                    provider,
                    budget_usd: Number(budget),
                    max_input_tokens: Number(maxInput),
                    max_output_tokens: Number(maxOutput),
                    ...buildOptions,
                    share_screenshots:
                      buildOptions.share_screenshots && (provider !== 'local' || config.local_vision),
                  }}
                />
              )}
              {tab === 'mobile' && (
                <MobilePanel
                  key={project.id}
                  project={project}
                  config={config}
                  running={running}
                  perform={perform}
                  launch={launch}
                />
              )}
              {['packages', 'visual', 'release'].includes(tab) && (
                <BuildTools
                  tab={tab}
                  project={project}
                  config={config}
                  running={running}
                  perform={perform}
                  launch={launch}
                  onContinue={() => {
                    setMode('coder');
                    setPrompt(
                      'Continue the previous app request using the approved dependencies. Complete the implementation and run all required checks.',
                    );
                  }}
                  onValidate={() => perform(() => launch(`/projects/${id}/validate`))}
                />
              )}
              {tab === 'settings' && (
                <SettingsPanel
                  key={project.id}
                  project={project}
                  config={config}
                  running={running}
                  refresh={() => refreshProject(id)}
                  onOpenGlobalSettings={() => setModal('global-settings')}
                />
              )}
              {tab === 'preview' && (
                <>
                  <div className="browser-toolbar">
                    <div className="traffic-lights">
                      <i />
                      <i />
                      <i />
                    </div>
                    <div className="address">
                      <ShieldCheck size={12} />
                      {project.preview_url || 'Preview is stopped'}
                    </div>
                    <button
                      className="icon-button"
                      title="Reload preview"
                      aria-label="Reload preview"
                      onClick={() => setPreviewKey(k => k + 1)}>
                      <RefreshCw size={14} />
                    </button>
                    {project.preview_url && (
                      <a
                        className="icon-button"
                        href={project.preview_url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label="Open preview in a new tab">
                        <ArrowUpRight size={15} />
                      </a>
                    )}
                  </div>
                  <div className="preview-content">
                    {project.preview_url ? (
                      <iframe
                        key={previewKey}
                        title={`${project.name} app preview`}
                        src={project.preview_url}
                        sandbox="allow-scripts allow-forms allow-same-origin"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <div className="preview-empty">
                        <div className="preview-empty-icon">
                          <Monitor size={31} />
                        </div>
                        <span className="eyebrow">YOUR APP LIVES HERE</span>
                        <h2>Make room for an idea.</h2>
                        <p>
                          Start your sandbox to see the React app
                          <br />
                          and its Python backend running together.
                        </p>
                        <button
                          className="primary"
                          disabled={running}
                          onClick={() => perform(() => launch(`/projects/${id}/preview/start`))}>
                          {running ? <Loader2 className="spin" size={15} /> : <Play size={15} />} Start
                          preview
                        </button>
                        <div className="preview-facts">
                          <span>
                            <Check size={12} /> Isolated containers
                          </span>
                          <span>
                            <Check size={12} /> Persistent database
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="preview-footer">
                    <span>
                      <span className={'status-dot ' + (!project.preview_url ? 'off' : '')} />
                      {project.preview_url ? 'Preview address available' : 'Ready when you are'}
                    </span>
                    <button
                      disabled={running}
                      onClick={() =>
                        perform(() =>
                          launch(`/projects/${id}/preview/${project.preview_url ? 'stop' : 'start'}`),
                        )
                      }>
                      {project.preview_url ? <Square size={11} /> : <Play size={11} />}{' '}
                      {project.preview_url ? 'Stop sandbox' : 'Start sandbox'}
                    </button>
                  </div>
                </>
              )}
              {tab === 'code' && (
                <div className="code-layout">
                  <nav aria-label="Source files" className="file-list">
                    {paths.map(item => {
                      const filePath = typeof item === 'string' ? item : item?.path || '';
                      return (
                        <button
                          key={filePath}
                          className={selectedPath === filePath ? 'selected' : ''}
                          onClick={() => readFile(filePath)}>
                          <FileCode2 size={13} />
                          <span>{filePath}</span>
                        </button>
                      );
                    })}
                  </nav>
                  <div className="source-pane">
                    <div className="source-title">
                      {selectedPath || 'Select a file'}
                      <span>READ ONLY</span>
                    </div>
                    <pre>
                      {source || 'Browse your project source. Ask the agent to make changes through chat.'}
                    </pre>
                  </div>
                </div>
              )}
              {tab === 'logs' && (
                <div className="logs-pane">
                  <div className="source-title">
                    Container logs
                    <button onClick={loadLogs}>
                      <RefreshCw size={13} /> Refresh
                    </button>
                  </div>
                  <pre>{logs || 'Loading logs…'}</pre>
                </div>
              )}
              {tab === 'versions' && (
                <div className="versions">
                  <h2>A history you can return to.</h2>
                  <p>
                    Source snapshots are saved before and after every AI build. Restoring source preserves
                    your database data.
                  </p>
                  {project.versions.map(v => (
                    <div className="version" key={v.id}>
                      <span className="version-icon">
                        <History size={17} />
                      </span>
                      <div>
                        <strong>{v.label}</strong>
                        <small>{date(v.created_at)}</small>
                      </div>
                      <button disabled={running} onClick={() => setModal({ restore: v })}>
                        Restore
                      </button>
                    </div>
                  ))}
                </div>
              )}
              {tab === 'data' && (
                <div className="data-pane">
                  <div className="data-heading">
                    <div>
                      <span className="eyebrow">POSTGRESQL SAFETY</span>
                      <h2>Checks, migrations, and backups.</h2>
                      <p>
                        Validation uses an isolated test database before applying numbered migrations to your
                        preview database. A verified backup is created first.
                      </p>
                    </div>
                    <button
                      className="primary"
                      disabled={running}
                      onClick={() => perform(() => launch(`/projects/${id}/validate`))}>
                      {running ? <Loader2 className="spin" size={15} /> : <ShieldCheck size={15} />} Run all
                      checks
                    </button>
                  </div>
                  <div className="validation-card">
                    <div>
                      <span className={'validation-status ' + (project.last_validation?.status || 'none')}>
                        {project.last_validation?.status === 'passed' ? (
                          <Check size={13} />
                        ) : project.last_validation?.status === 'failed' ? (
                          <X size={13} />
                        ) : (
                          <ShieldCheck size={13} />
                        )}{' '}
                        {project.last_validation?.status === 'passed'
                          ? 'Current source passed'
                          : project.last_validation?.status === 'failed'
                            ? 'Last validation failed'
                            : project.last_validation?.status === 'stale'
                              ? 'Source changed after validation'
                              : 'Not validated yet'}
                      </span>
                      <small>
                        {project.last_validation?.status === 'stale'
                          ? 'Run checks again before saving to GitHub.'
                          : project.last_validation?.created_at
                            ? date(project.last_validation.created_at)
                            : 'GitHub saving stays locked until the current source passes.'}
                      </small>
                    </div>
                    {project.last_validation?.checks?.length > 0 && (
                      <div className="check-grid">
                        {project.last_validation.checks.map(check => (
                          <span className={check.status} key={check.name}>
                            {check.status === 'passed' ? <Check size={11} /> : <X size={11} />} {check.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="backup-title">
                    <div>
                      <h3>Database backups</h3>
                      <p>
                        Backups are local custom-format PostgreSQL dumps with a recorded SHA-256 checksum.
                      </p>
                    </div>
                    <button
                      disabled={running}
                      onClick={() => perform(() => launch(`/projects/${id}/backups`))}>
                      <Database size={14} /> Create backup
                    </button>
                  </div>
                  <div className="backup-list">
                    {project.backups.length ? (
                      project.backups.map(backup => (
                        <div className="backup" key={backup.id}>
                          <span className="version-icon">
                            <Database size={16} />
                          </span>
                          <div>
                            <strong>{backup.label}</strong>
                            <small>
                              {date(backup.created_at)} · {(backup.bytes / 1024).toFixed(1)} KB · verified
                            </small>
                          </div>
                          <button disabled={running} onClick={() => setModal({ backup })}>
                            Restore
                          </button>
                        </div>
                      ))
                    ) : (
                      <div className="backup-empty">
                        No database backups yet. One is created automatically before validated migrations.
                      </div>
                    )}
                  </div>
                </div>
              )}
              {tab === 'documents' && (
                <DocumentsPanel
                  project={project}
                  id={id}
                  running={running}
                  busy={busy}
                  perform={perform}
                  launch={launch}
                  searchDocuments={searchDocuments}
                  documentQuery={documentQuery}
                  setDocumentQuery={setDocumentQuery}
                  documentResults={documentResults}
                />
              )}
              {tab === 'files' && (
                <FilesPanel
                  project={project}
                  id={id}
                  config={config}
                  running={running}
                  perform={perform}
                  launch={launch}
                  setMode={setMode}
                  setPrompt={setPrompt}
                />
              )}
              {tab === 'recovery' && (
                <RecoveryPanel
                  project={project}
                  running={running}
                  perform={perform}
                  setModal={setModal}
                  setRecoveryPassword={setRecoveryPassword}
                  setRecoveryConfirm={setRecoveryConfirm}
                  openRecoveryImport={openRecoveryImport}
                />
              )}
            </section>
          </div>
        )}
      </main>

      {modal && (
        <div className="modal-backdrop" onClick={() => !busy && closeModal()}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
            onClick={e => e.stopPropagation()}>
            <button className="modal-close icon-button" aria-label="Close dialog" onClick={closeModal}>
              <X size={18} />
            </button>
            {modal === 'build-options' && (
              <>
                <span className="modal-icon">
                  <SlidersHorizontal size={24} />
                </span>
                <h2 id="modal-title">Build, check, repair.</h2>
                <p>Choose how much autonomy to give the next coding run.</p>
                <BuildOptions
                  options={buildOptions}
                  setOptions={setBuildOptions}
                  provider={provider}
                  config={config}
                />
                <button className="primary wide" onClick={closeModal}>
                  Save build controls
                </button>
              </>
            )}
            {modal === 'new' && (
              <form onSubmit={create}>
                <span className="modal-icon">
                  <Plus size={23} />
                </span>
                <h2 id="modal-title">A new beginning.</h2>
                <p>Name your project. We’ll prepare a working app with React, Python, and PostgreSQL.</p>
                <label>
                  PROJECT NAME
                  <input
                    autoFocus
                    required
                    maxLength={80}
                    value={name}
                    onChange={e => setName(e.target.value)}
                    placeholder="My next great idea"
                  />
                </label>
                <label>
                  STARTING POINT
                  <select value={profile} onChange={e => setProfile(e.target.value)}>
                    <option value="accounts">Accounts & billing · login, roles, payments, operations</option>
                    <option value="starter">Simple notebook · minimal starter</option>
                  </select>
                </label>
                <p className="muted">
                  {profile === 'accounts'
                    ? 'Includes private accounts and a production deployment kit. Payments and integrations stay off in previews.'
                    : 'A small anonymous notebook you can extend.'}
                </p>
                <button className="primary wide" disabled={busy || !name.trim()}>
                  {busy ? <Loader2 size={16} className="spin" /> : <Plus size={16} />} Create project
                </button>
              </form>
            )}
            {modal === 'github' && (
              <form
                onSubmit={
                  githubReview
                    ? e => {
                        e.preventDefault();
                        publishGithub();
                      }
                    : reviewGithub
                }>
                <span className="modal-icon">
                  <Github size={24} />
                </span>
                <h2 id="modal-title">Review before GitHub.</h2>
                <p>
                  {project.repo
                    ? `Compare the current source with ${project.repo}. Remote-only files are preserved, and any remote change since your last save blocks the write.`
                    : 'Review the exact source changes, then create a new private repository in the GitHub account signed in through gh.'}
                </p>
                <label>
                  REPOSITORY NAME
                  <input
                    autoFocus
                    required
                    value={repoName}
                    disabled={!!project.repo || !!githubReview}
                    pattern="[A-Za-z0-9][A-Za-z0-9._-]{0,99}"
                    onChange={e => {
                      setRepoName(e.target.value);
                      setGithubReview(null);
                    }}
                  />
                </label>
                <label>
                  COMMIT MESSAGE
                  <input
                    required
                    maxLength={200}
                    value={commitMessage}
                    onChange={e => setCommitMessage(e.target.value)}
                  />
                </label>
                {githubReview ? (
                  <div className="github-review">
                    <div className="review-summary">
                      <strong>
                        {githubReview.changes.length} local change
                        {githubReview.changes.length === 1 ? '' : 's'}
                      </strong>
                      <span>
                        {githubReview.preserved_remote_files} remote-only file
                        {githubReview.preserved_remote_files === 1 ? '' : 's'} preserved
                      </span>
                    </div>
                    {githubReview.conflicts.length > 0 && (
                      <div className="conflict-list">
                        {githubReview.conflicts.map(item => (
                          <p key={item}>! {item}</p>
                        ))}
                      </div>
                    )}
                    <div className="change-list">
                      {githubReview.changes.map(change => (
                        <details key={change.path}>
                          <summary>
                            <span className={'change-kind ' + change.change}>{change.change}</span>
                            {change.path}
                          </summary>
                          <pre>
                            {change.diff || `${change.path} has no text diff.`}
                            {change.truncated ? '\n[Diff truncated in review.]' : ''}
                          </pre>
                        </details>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="publish-note">
                    <ShieldCheck size={15} />
                    <span>
                      Saving is available only after the current source passes syntax, build, test, migration,
                      backup, and health checks.
                    </span>
                  </div>
                )}
                <button className="primary wide" disabled={busy || !!githubReview?.conflicts?.length}>
                  {busy ? <Loader2 size={16} className="spin" /> : <Github size={16} />}{' '}
                  {githubReview
                    ? project.repo
                      ? 'Confirm reviewed save'
                      : 'Create private repository & save'
                    : 'Review changes'}
                </button>
                {githubReview && (
                  <button
                    type="button"
                    className="secondary wide"
                    disabled={busy}
                    onClick={() => setGithubReview(null)}>
                    Refresh review
                  </button>
                )}
              </form>
            )}
            {modal === 'global-settings' && (
              <GlobalSettingsModal
                config={config}
                provider={provider}
                setProvider={setProvider}
                budget={budget}
                setBudget={setBudget}
                maxInput={maxInput}
                setMaxInput={setMaxInput}
                maxOutput={maxOutput}
                setMaxOutput={setMaxOutput}
                buildOptions={buildOptions}
                setBuildOptions={setBuildOptions}
                onClose={() => setModal(null)}
                onShowDiagnostics={showDiagnostics}
                onSaveNotice={msg => setNotice(msg)}
              />
            )}
            {modal === 'budget' && (
              <form
                onSubmit={e => {
                  e.preventDefault();
                  setModal(null);
                }}>
                <span className="modal-icon">
                  <CircleDollarSign size={24} />
                </span>
                <h2 id="modal-title">Bound every build.</h2>
                <p>
                  Local Foundry checks conservative limits before each model call and stops safely when actual
                  provider usage reaches one of them. Completed file edits remain available.
                </p>
                <div className="limit-grid">
                  <label>
                    MAX ESTIMATED COST (USD)
                    <input
                      type="number"
                      min={provider === 'local' ? '0' : '0.10'}
                      max="100"
                      step="0.10"
                      required
                      value={budget}
                      onChange={e => setBudget(e.target.value)}
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
                      value={maxInput}
                      onChange={e => setMaxInput(e.target.value)}
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
                      value={maxOutput}
                      onChange={e => setMaxOutput(e.target.value)}
                    />
                  </label>
                </div>
                <div className="publish-note">
                  <ShieldCheck size={15} />
                  <span>
                    {provider === 'local'
                      ? 'Local AI has no API charge; token caps still protect memory and run time.'
                      : 'Cost is estimated with the displayed standard rates. Your provider’s billing record is authoritative.'}
                  </span>
                </div>
                <button className="primary wide">Save build limits</button>
              </form>
            )}
            {modal === 'export-recovery' && (
              <form
                onSubmit={e => {
                  e.preventDefault();
                  if (recoveryPassword !== recoveryConfirm) {
                    setError('Recovery passwords do not match.');
                    return;
                  }
                  perform(async () => {
                    await launch(`/projects/${id}/recovery`, { password: recoveryPassword });
                    setRecoveryPassword('');
                    setRecoveryConfirm('');
                    setModal(null);
                  });
                }}>
                <span className="modal-icon">
                  <Archive size={24} />
                </span>
                <h2 id="modal-title">Encrypt a full recovery.</h2>
                <p>
                  This includes source, versions, chat history, and the current PostgreSQL database. The
                  password is used in memory and is never stored.
                </p>
                <label>
                  RECOVERY PASSWORD
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={200}
                    required
                    value={recoveryPassword}
                    onChange={e => setRecoveryPassword(e.target.value)}
                  />
                </label>
                <label>
                  CONFIRM PASSWORD
                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={200}
                    required
                    value={recoveryConfirm}
                    onChange={e => setRecoveryConfirm(e.target.value)}
                  />
                </label>
                <div className="publish-note">
                  <ShieldCheck size={15} />
                  <span>Use a unique password and store it separately. There is no password reset.</span>
                </div>
                <button
                  className="primary wide"
                  disabled={busy || recoveryPassword.length < 12 || recoveryPassword !== recoveryConfirm}>
                  <Archive size={16} /> Create encrypted export
                </button>
              </form>
            )}
            {modal === 'import' && (
              <form onSubmit={doImportRecovery}>
                <span className="modal-icon">
                  <Upload size={24} />
                </span>
                <h2 id="modal-title">Import a recovery.</h2>
                <p>
                  A new local project is created. Existing projects are never overwritten, and imported GitHub
                  connections are intentionally left disconnected.
                </p>
                <label>
                  RECOVERY ARCHIVE
                  <input
                    type="file"
                    accept=".lfr,application/octet-stream"
                    required
                    onChange={e => setRecoveryFile(e.target.files?.[0] || null)}
                  />
                </label>
                <label>
                  NEW PROJECT NAME (OPTIONAL)
                  <input
                    maxLength={80}
                    value={recoveryName}
                    onChange={e => setRecoveryName(e.target.value)}
                    placeholder="Use the archived name"
                  />
                </label>
                <label>
                  RECOVERY PASSWORD
                  <input
                    type="password"
                    autoComplete="current-password"
                    minLength={12}
                    maxLength={200}
                    required
                    value={recoveryPassword}
                    onChange={e => setRecoveryPassword(e.target.value)}
                  />
                </label>
                <label>
                  CONFIRM PASSWORD
                  <input
                    type="password"
                    autoComplete="current-password"
                    minLength={12}
                    maxLength={200}
                    required
                    value={recoveryConfirm}
                    onChange={e => setRecoveryConfirm(e.target.value)}
                  />
                </label>
                <button
                  className="primary wide"
                  disabled={
                    busy ||
                    !recoveryFile ||
                    recoveryPassword.length < 12 ||
                    recoveryPassword !== recoveryConfirm
                  }>
                  {busy ? <Loader2 size={16} className="spin" /> : <Upload size={16} />} Import as new project
                </button>
              </form>
            )}
            {modal === 'diagnostics' && diagnostics && (
              <>
                <span className="modal-icon">
                  <Activity size={24} />
                </span>
                <h2 id="modal-title">System diagnostics.</h2>
                <p>
                  {diagnostics.platform.system} {diagnostics.platform.release} ·{' '}
                  {diagnostics.platform.machine} ·{' '}
                  {(diagnostics.disk_free_bytes / 1024 / 1024 / 1024).toFixed(1)} GB free
                </p>
                <div className="publish-note">
                  <ShieldCheck size={15} />
                  <span>
                    {diagnostics.offline_readiness?.ready
                      ? 'Offline preflight passed. Prove it with a disconnected local build.'
                      : 'Offline preflight is not complete. Cache images, load the exact local model, and enable OFFLINE_ONLY.'}
                  </span>
                </div>
                <div className="diagnostic-list">
                  {Object.entries(diagnostics.checks).map(([key, check]) => (
                    <div key={key}>
                      <span className={'diagnostic-dot ' + check.status} />
                      <strong>{key.replaceAll('_', ' ')}</strong>
                      <small>{check.detail}</small>
                    </div>
                  ))}
                </div>
                <button className="secondary wide" onClick={showDiagnostics} disabled={busy}>
                  <RefreshCw size={14} /> Run again
                </button>
              </>
            )}
            {modal.restore && (
              <>
                <span className="modal-icon">
                  <History size={24} />
                </span>
                <h2 id="modal-title">Restore this version?</h2>
                <p>
                  {modal.restore.label} · {date(modal.restore.created_at)}. Your current source will be backed
                  up first. The sandbox will stop; database contents stay as they are.
                </p>
                <button
                  className="primary wide"
                  disabled={busy}
                  onClick={() =>
                    perform(async () => {
                      await launch(`/projects/${id}/restore/${modal.restore.id}`);
                      setModal(null);
                    })
                  }>
                  <History size={16} /> Restore source
                </button>
              </>
            )}
            {modal.backup && (
              <>
                <span className="modal-icon">
                  <Database size={24} />
                </span>
                <h2 id="modal-title">Restore this database?</h2>
                <p>
                  {modal.backup.label} · {date(modal.backup.created_at)}. The preview will stop, and a fresh
                  safeguard backup of the current database will be created before this dump is verified and
                  restored.
                </p>
                <button
                  className="primary wide"
                  disabled={busy}
                  onClick={() =>
                    perform(async () => {
                      await launch(`/projects/${id}/backups/${modal.backup.id}/restore`);
                      setModal(null);
                    })
                  }>
                  <Database size={16} /> Safeguard & restore
                </button>
              </>
            )}
            {error && (
              <p className="modal-error" role="alert">
                {error}
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
