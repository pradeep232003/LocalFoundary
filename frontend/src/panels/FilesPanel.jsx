import { Check, Files, RotateCcw, Wand2 } from 'lucide-react';
import { date } from '../format';

export default function FilesPanel({ project, id, config, running, perform, launch, setMode, setPrompt }) {
  return (
    <div className="tool-pane">
      <div className="data-heading">
        <div>
          <span className="eyebrow">REVERSIBLE AUTOMATION</span>
          <h2>Preview every file operation.</h2>
          <p>
            The Files agent sees filenames and metadata only. It cannot read contents or make changes until
            you approve a dry run. “Trash” is recoverable.
          </p>
        </div>
        <button
          className="primary"
          onClick={() => {
            setMode('files');
            setPrompt(
              'Organize the managed files into clear folders. Preserve ambiguous filenames and explain the plan.',
            );
          }}>
          <Wand2 size={14} /> Draft a plan
        </button>
      </div>
      <div className="folder-card">
        <Files size={18} />
        <div>
          <strong>Managed files folder</strong>
          <small>{config.files_folder}</small>
        </div>
        <span>Scoped</span>
      </div>
      <div className="plan-list">
        {project.file_plans.length ? (
          project.file_plans.map(plan => (
            <article className="file-plan" key={plan.id}>
              <div className="plan-heading">
                <div>
                  <strong>{plan.prompt}</strong>
                  <small>
                    {date(plan.created_at)} · {plan.operations.length} operations
                  </small>
                </div>
                <span className={'plan-status ' + plan.status}>{plan.status}</span>
              </div>
              <div className="operation-list">
                {plan.operations.map((operation, index) => (
                  <code key={index}>
                    {operation.op} · {operation.source || operation.destination}
                    {operation.op === 'move' ? ` → ${operation.destination}` : ''}
                  </code>
                ))}
              </div>
              <div className="plan-actions">
                {plan.status === 'planned' && (
                  <button
                    disabled={running}
                    onClick={() => perform(() => launch(`/projects/${id}/file-plans/${plan.id}/apply`))}>
                    <Check size={13} /> Apply reviewed plan
                  </button>
                )}
                {plan.status === 'applied' && (
                  <button
                    disabled={running}
                    onClick={() => perform(() => launch(`/projects/${id}/file-plans/${plan.id}/undo`))}>
                    <RotateCcw size={13} /> Undo
                  </button>
                )}
              </div>
            </article>
          ))
        ) : (
          <div className="backup-empty">
            No plans yet. Choose the Files agent, describe an organization goal, and review its proposal here.
          </div>
        )}
      </div>
    </div>
  );
}
