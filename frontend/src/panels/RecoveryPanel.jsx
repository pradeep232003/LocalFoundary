import { Archive, Download, ShieldCheck, Upload } from 'lucide-react';
import { downloadRecovery } from '../api';
import { date } from '../format';

export default function RecoveryPanel({
  project,
  running,
  perform,
  setModal,
  setRecoveryPassword,
  setRecoveryConfirm,
  openRecoveryImport,
}) {
  return (
    <div className="tool-pane">
      <div className="data-heading">
        <div>
          <span className="eyebrow">PORTABLE RECOVERY</span>
          <h2>One encrypted project archive.</h2>
          <p>
            Recovery exports contain current source, source versions, chat history, and a verified PostgreSQL
            dump. GitHub credentials and API keys are never included.
          </p>
        </div>
        <button
          className="primary"
          disabled={running}
          onClick={() => {
            setRecoveryPassword('');
            setRecoveryConfirm('');
            setModal('export-recovery');
          }}>
          <Archive size={14} /> Create export
        </button>
      </div>
      <div className="recovery-note">
        <ShieldCheck size={18} />
        <div>
          <strong>A password is required every time.</strong>
          <p>Local Foundry never stores it. Losing the password makes the archive unrecoverable.</p>
        </div>
      </div>
      <div className="backup-title">
        <div>
          <h3>Encrypted exports</h3>
          <p>Keep at least one copy away from this computer.</p>
        </div>
        <button onClick={openRecoveryImport}>
          <Upload size={14} /> Import archive
        </button>
      </div>
      <div className="backup-list">
        {project.recovery_exports.length ? (
          project.recovery_exports.map(item => (
            <div className="backup" key={item.id}>
              <span className="version-icon">
                <Archive size={16} />
              </span>
              <div>
                <strong>{item.filename}</strong>
                <small>
                  {date(item.created_at)} · {(item.bytes / 1024 / 1024).toFixed(2)} MB
                </small>
              </div>
              <button onClick={() => perform(() => downloadRecovery(project, item))}>
                <Download size={13} /> Download
              </button>
            </div>
          ))
        ) : (
          <div className="backup-empty">No encrypted recovery exports yet.</div>
        )}
      </div>
    </div>
  );
}
