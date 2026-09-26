import { useEffect, useState } from 'react';
import { request } from './api';

const fields = [
  ['requirements', 'Requirements'],
  ['architecture', 'Architecture'],
  ['data_model', 'Data model'],
  ['decisions', 'Decisions'],
  ['open_questions', 'Open questions'],
];
const empty = () => ({ title: '', prompt: '', acceptance: '' });

export default function ProjectContinuity({
  tab,
  project,
  running,
  perform,
  launch,
  refresh,
  buildSettings,
  providerReady,
}) {
  const normalizeBody = (raw) => {
    const b = { ...(raw || {}) };
    if (!b.open_questions && b.questions) {
      b.open_questions = b.questions;
    }
    return b;
  };

  const [body, setBody] = useState(() => normalizeBody(project.context?.body));
  const [revision, setRevision] = useState(project.context?.revision || 0);
  const [savedNotice, setSavedNotice] = useState('');
  const [title, setTitle] = useState('');
  const [items, setItems] = useState([empty()]);
  const [reviewed, setReviewed] = useState({});
  useEffect(() => {
    setBody(normalizeBody(project.context?.body));
    setRevision(project.context?.revision || 0);
  }, [project.id, project.context?.revision, project.context?.updated_at]);
  useEffect(() => {
    setReviewed({});
  }, [project.id, project.source_digest, project.feature_plans?.map(p => p.updated_at).join(',')]);
  if (tab === 'context')
    return (
      <div className="tool-pane upgrade-pane continuity">
        <span className="eyebrow">PROJECT MEMORY</span>
        <h2>Keep the decisions that matter.</h2>
        <p>
          Saved context follows this project into future builds and encrypted recovery exports. Keep
          credentials in private settings.
        </p>
        {savedNotice && (
          <div className="notice-banner" style={{ margin: '12px 0' }}>
            <span>✓ {savedNotice}</span>
          </div>
        )}
        <form
          onSubmit={e => {
            e.preventDefault();
            perform(async () => {
              const res = await request(`/projects/${project.id}/context`, { body, revision });
              if (res?.revision) setRevision(res.revision);
              setSavedNotice(`Context saved (revision ${res?.revision ?? revision + 1}).`);
              setTimeout(() => setSavedNotice(''), 3500);
              await refresh();
            });
          }}>
          {fields.map(([key, label]) => (
            <label key={key}>
              {label}
              <textarea
                maxLength={6000}
                value={body[key] || ''}
                onChange={e => setBody({ ...body, [key]: e.target.value })}
                disabled={running}
                placeholder={`Document project ${label.toLowerCase()} here...`}
              />
            </label>
          ))}
          <button className="primary" disabled={running}>
            Save project context
          </button>
        </form>
        <h3>Agent notes</h3>
        <p>Notes are reference material. Your requirements take precedence.</p>
        {(() => {
          const notes = Array.isArray(project.context?.agent_notes)
            ? project.context.agent_notes
            : typeof project.context?.agent_notes === 'string' && project.context.agent_notes.trim()
            ? [{ text: project.context.agent_notes, at: project.context.updated_at || new Date().toISOString() }]
            : [];
          if (!notes.length) {
            return (
              <p className="muted" style={{ fontStyle: 'italic', fontSize: '13px' }}>
                No agent notes recorded yet. Notes captured during AI build runs will appear here.
              </p>
            );
          }
          return notes.map((note, i) => {
            const noteText = typeof note === 'string' ? note : (note?.text || '');
            const noteAt = typeof note === 'object' && note?.at ? note.at : null;
            return (
              <article className="file-plan" key={i}>
                <p>{noteText}</p>
                {noteAt && <small>{new Date(noteAt).toLocaleString()}</small>}
              </article>
            );
          });
        })()}
      </div>
    );
  return (
    <div className="tool-pane upgrade-pane continuity">
      <span className="eyebrow">FEATURE ROADMAP</span>
      <h2>Build in testable milestones.</h2>
      <p>
        Each milestone saves source snapshots and runs validation. Usage carries across milestones and
        resumes. After an interruption, review partial source and data changes before continuing.
      </p>
      {(project.feature_plans || []).map(plan => (
        <article className="file-plan" key={plan.id}>
          <div className="plan-heading">
            <strong>{plan.title}</strong>
            <span className="plan-status">{plan.status.replaceAll('_', ' ')}</span>
          </div>
          <ol>
            {plan.milestones.map(item => (
              <li key={item.id}>
                <strong>{item.title}</strong> · {item.status.replaceAll('_', ' ')}
                <p>{item.acceptance}</p>
                {item.result && (
                  <details>
                    <summary>Result</summary>
                    <pre>{item.result}</pre>
                  </details>
                )}
              </li>
            ))}
          </ol>
          <p>
            {plan.usage?.input_tokens || 0} input tokens · {plan.usage?.output_tokens || 0} output tokens ·
            estimated ${Number(plan.usage?.estimated_usd || 0).toFixed(4)} used
          </p>
          {plan.checkpoint?.phase && (
            <details>
              <summary>Last checkpoint</summary>
              <pre>{JSON.stringify(plan.checkpoint, null, 2)}</pre>
            </details>
          )}
          {!['completed', 'running'].includes(plan.status) && (
            <>
              <label className="check-option">
                <input
                  type="checkbox"
                  checked={!!reviewed[plan.id]}
                  disabled={running}
                  onChange={e => setReviewed({ ...reviewed, [plan.id]: e.target.checked })}
                />
                <span>I reviewed this plan, the current source, and any partial data changes.</span>
              </label>
              <button
                className="primary"
                disabled={running || !providerReady || !reviewed[plan.id]}
                onClick={() =>
                  perform(() =>
                    launch(`/projects/${project.id}/plans/${plan.id}/start`, {
                      ...buildSettings,
                      reviewed: true,
                      source_digest: project.source_digest,
                    }),
                  )
                }>
                {plan.status === 'ready' ? 'Start milestones' : 'Resume remaining milestones'}
              </button>
            </>
          )}
        </article>
      ))}
      <details open={!project.feature_plans?.length}>
        <summary>Create a feature plan</summary>
        <form
          onSubmit={e => {
            e.preventDefault();
            perform(async () => {
              await request(`/projects/${project.id}/plans`, { title, milestones: items });
              setTitle('');
              setItems([empty()]);
              await refresh();
            });
          }}>
          <label>
            Plan title
            <input required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} />
          </label>
          {items.map((item, i) => (
            <fieldset key={i}>
              <legend>Milestone {i + 1}</legend>
              {[
                ['title', 'Title', 120],
                ['prompt', 'Requested change', 6000],
                ['acceptance', 'Acceptance criteria', 3000],
              ].map(([key, label, max]) => (
                <label key={key}>
                  {label}
                  <textarea
                    required
                    maxLength={max}
                    value={item[key]}
                    onChange={e =>
                      setItems(items.map((row, n) => (n === i ? { ...row, [key]: e.target.value } : row)))
                    }
                  />
                </label>
              ))}
              {items.length > 1 && (
                <button type="button" onClick={() => setItems(items.filter((_, n) => n !== i))}>
                  Remove milestone
                </button>
              )}
            </fieldset>
          ))}
          <div className="plan-actions">
            <button
              type="button"
              disabled={items.length >= 12 || running}
              onClick={() => setItems([...items, empty()])}>
              Add milestone
            </button>
            <button className="primary" disabled={running}>
              Save plan
            </button>
          </div>
        </form>
      </details>
      <p>
        Uses the selected model and Build Limits as a total allowance, including prior usage. Resuming an
        interrupted milestone disables arbitrary shell commands. Provider responses lost during interruption
        reserve estimated usage.
      </p>
    </div>
  );
}
