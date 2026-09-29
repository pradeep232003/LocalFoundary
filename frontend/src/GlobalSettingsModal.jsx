import { useState } from 'react';
export default function GlobalSettingsModal({config,provider,setProvider,budget,setBudget,maxInput,setMaxInput,maxOutput,setMaxOutput,buildOptions,setBuildOptions,onClose,onShowDiagnostics,onSaveNotice}) {
  const [selected,setSelected]=useState(provider);
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="settings-heading">
    <button onClick={onClose}>Close</button><h2 id="settings-heading">Model and build settings</h2>
    <p>{config?.offline_only ? 'Offline-only mode is enforced by the backend.' : 'Cloud providers can use the network and incur charges.'}</p>
    <p>Set provider keys, LOCAL_API_BASE, LOCAL_MODEL and OFFLINE_ONLY in the private configuration file, then restart. Keys stay on the backend.</p>
    <label>Provider<select value={selected} onChange={e=>setSelected(e.target.value)}>{Object.entries(config?.providers || {}).map(([key,p])=><option key={key} value={key} disabled={!p.configured}>{key} · {p.model || 'not configured'}</option>)}</select></label>
    <label>Maximum estimated cost (USD)<input type="number" min="0.01" max="100" step="0.01" value={budget} onChange={e=>setBudget(e.target.value)}/></label>
    <label>Input token limit<input type="number" min="1000" value={maxInput} onChange={e=>setMaxInput(e.target.value)}/></label>
    <label>Output token limit<input type="number" min="1000" value={maxOutput} onChange={e=>setMaxOutput(e.target.value)}/></label>
    <label><input type="checkbox" checked={buildOptions.browser_checks} onChange={e=>setBuildOptions({...buildOptions,browser_checks:e.target.checked})}/>Run browser checks</label>
    <button onClick={()=>{setProvider(selected);onSaveNotice('Build settings updated for this session.');onClose();}}>Apply</button>
    <button onClick={onShowDiagnostics}>Check local prerequisites</button>
  </section></div>;
}
