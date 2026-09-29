import React, { useEffect, useState } from 'react';
import { request } from './api';
const modes = [
  { id: 'coder', name: 'Coding', description: 'Edit project source with a model, then run the sandbox validation gates.' },
  { id: 'documents', name: 'Document research', description: 'Search indexed local documents and return citations. Documents are read-only.' },
  { id: 'files', name: 'File planning', description: 'Propose changes in the approved files folder. Review and apply the plan in the Files tab.' },
];
export default function AgentBuilder({ onReturnToAppBuilder, projects = [], project, config, onRunStarted }: any) {
  const [projectId, setProjectId] = useState(project?.id || projects[0]?.id || '');
  const [mode, setMode] = useState('coder');
  const [provider, setProvider] = useState(config?.offline_only ? 'local' : Object.keys(config?.providers || {}).find(k => config.providers[k].configured) || 'local');
  const [prompt, setPrompt] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!projectId && projects.length) setProjectId(projects[0].id); }, [projects, projectId]);
  async function run(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const result = await request(`/projects/${projectId}/build`, { prompt, mode, provider });
      onRunStarted(projectId, mode, result);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not start agent.'); }
    finally { setBusy(false); }
  }
  return <section style={{ padding: 32, maxWidth: 1000, margin: 'auto' }}>
    <button onClick={onReturnToAppBuilder}>Return to builder</button><h1>Agent Studio</h1>
    <p>Run a task using your configured model. Progress, tool output, usage and failures appear in the project workspace.</p>
    <form onSubmit={run}>
      <label>Project<select value={projectId} onChange={e => setProjectId(e.target.value)}>{projects.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label>Task<select value={mode} onChange={e => setMode(e.target.value)}>{modes.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
      <p>{modes.find(m => m.id === mode)?.description}</p>
      <label>Model provider<select value={provider} onChange={e => setProvider(e.target.value)}>{Object.entries(config?.providers || {}).map(([key, value]: [string, any]) => <option key={key} value={key} disabled={!value.configured}>{key} · {value.model || 'not configured'}</option>)}</select></label>
      <label>Task instructions<textarea required maxLength={12000} rows={6} value={prompt} onChange={e => setPrompt(e.target.value)} /></label>
      <button className="primary" disabled={busy || !projectId || !config?.providers?.[provider]?.configured}>{busy ? 'Starting…' : 'Run agent'}</button>
    </form>
    {!projects.length && <p>Create a project in the builder first.</p>}
    <p>Shopping, travel, inbox and financial account connectors are not installed. Live prices, bookings, messages and transactions cannot be verified or executed here.</p>
    {error && <p role="alert">{error}</p>}
  </section>;
}
