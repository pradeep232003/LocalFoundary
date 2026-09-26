import { useEffect, useState } from 'react';
import { Camera, Check, Download, Package, Play, ShieldCheck, Wand2 } from 'lucide-react';
import { request, downloadRelease } from './api';
import './upgrades.css';

export function BuildOptions({ options, setOptions, provider, config }) {
  const visionAllowed = provider !== 'local' || config?.local_vision;
  return (
    <div className="build-options">
      <label>
        MAXIMUM AUTOMATIC REPAIRS
        <select
          value={options.max_repairs}
          onChange={e => setOptions({ ...options, max_repairs: Number(e.target.value) })}>
          {[0, 1, 2, 3].map(n => (
            <option key={n} value={n}>
              {n === 0 ? 'Off — stop at the first failed check' : `${n} repair attempt${n > 1 ? 's' : ''}`}
            </option>
          ))}
        </select>
      </label>
      <label className="check-option">
        <input
          type="checkbox"
          checked={options.browser_checks}
          onChange={e => setOptions({ ...options, browser_checks: e.target.checked })}
        />
        <span>
          Require desktop and mobile browser checks
          <small>
            Uses the cached Playwright container. Checks rendering errors and horizontal overflow, and saves
            screenshots locally.
          </small>
        </span>
      </label>
      <label className="check-option">
        <input
          type="checkbox"
          disabled={!visionAllowed}
          checked={options.share_screenshots && visionAllowed}
          onChange={e => setOptions({ ...options, share_screenshots: e.target.checked })}
        />
        <span>
          Let the selected AI model see screenshots
          <small>
            {provider === 'local'
              ? visionAllowed
                ? 'Images go only to your loopback vision model.'
                : 'Set LOCAL_VISION=true for a tested image-capable local model.'
              : 'Preview pixels may contain app data. This sends them to your selected cloud AI provider and may incur input-token costs.'}
          </small>
        </span>
      </label>
      <div className="publish-note">
        <ShieldCheck size={16} />
        <span>
          Every repair shares the original budget. Package installation, GitHub saves, and deployment remain
          separate approval steps.
        </span>
      </div>
    </div>
  );
}

function Screenshot({ projectId, item }) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true,
      objectUrl;
    setUrl('');
    setError('');
    request(`/projects/${projectId}/visual/${item.id}`, undefined, { blob: true })
      .then(blob => {
        objectUrl = URL.createObjectURL(blob);
        if (active) setUrl(objectUrl);
        else URL.revokeObjectURL(objectUrl);
      })
      .catch(e => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [projectId, item.id]);
  return error ? (
    <p role="alert">{error}</p>
  ) : url ? (
    <img className="browser-evidence" src={url} alt={`${item.viewport} app screenshot of ${item.path}`} />
  ) : (
    <p>Loading screenshot…</p>
  );
}

export default function BuildTools({
  tab,
  project,
  config,
  running,
  perform,
  launch,
  onContinue,
  onValidate,
}) {
  const [allowNetwork, setAllowNetwork] = useState(false);
  const [path, setPath] = useState('/');
  const [viewport, setViewport] = useState('desktop');
  const [actions, setActions] = useState('[]');
  const [selected, setSelected] = useState(null);
  const [reviewed, setReviewed] = useState(false);
  useEffect(() => {
    setAllowNetwork(false);
    setSelected(null);
    setReviewed(false);
  }, [project.id, project.source_digest]);
  const requests = project.dependency_requests || [];
  const evidence = project.visual_checks || [];
  const item = evidence.find(row => row.id === selected) || evidence[0];
  const validated =
    project.last_validation?.status === 'passed' &&
    (project.profile !== 'accounts' ||
      (project.last_validation?.gate_version >= 6 &&
        project.last_validation?.browser_checks &&
        ['Protected security contracts', 'Authenticated user journeys'].every(name =>
          project.last_validation.checks?.some(c => c.name === name && c.status === 'passed'),
        )));
  if (tab === 'packages')
    return (
      <div className="tool-pane upgrade-pane">
        <span className="eyebrow">CONTROLLED DEPENDENCIES</span>
        <h2>More capability. Your approval.</h2>
        <p>
          Ask the coding agent for a feature that needs a package. It proposes exact npm or Python versions
          and pauses here. No model can approve its own installation.
        </p>
        <div className="release-warning">
          <Package size={18} />
          <p>
            Packages are third-party code. Review names and versions carefully. Downloads run in a separate
            image build with no app source, host folders, or provider keys. npm lifecycle scripts and Python
            source builds are disabled.
          </p>
        </div>
        <label className="check-option">
          <input
            type="checkbox"
            checked={allowNetwork && !config.offline_only}
            disabled={config.offline_only || running}
            onChange={e => setAllowNetwork(e.target.checked)}
          />
          <span>
            Allow registry downloads for this approval
            <small>
              {config.offline_only
                ? 'Offline mode: only already-cached runtime images can be applied.'
                : 'Unchecked means cached images only. Approval never opens preview network access.'}
            </small>
          </span>
        </label>
        <div className="plan-list">
          {requests.length ? (
            requests.map(row => (
              <article className="file-plan" key={row.id}>
                <div className="plan-heading">
                  <strong>{row.reason}</strong>
                  <span className="plan-status">{row.status}</span>
                </div>
                <div className="operation-list">
                  {row.packages.map(pkg => (
                    <code key={pkg.ecosystem + pkg.name}>
                      {pkg.ecosystem} · {pkg.name} {pkg.version}
                    </code>
                  ))}
                </div>
                {row.status === 'pending' && (
                  <div className="plan-actions">
                    <button
                      disabled={running}
                      onClick={() =>
                        perform(() => launch(`/projects/${project.id}/packages/${row.id}/reject`))
                      }>
                      Reject
                    </button>
                    <button
                      disabled={running}
                      onClick={() =>
                        perform(() =>
                          launch(`/projects/${project.id}/packages/${row.id}/approve`, {
                            allow_network: allowNetwork && !config.offline_only,
                          }),
                        )
                      }>
                      <Check size={13} /> Approve listed packages
                    </button>
                  </div>
                )}
              </article>
            ))
          ) : (
            <div className="backup-empty">No package requests yet. The existing stack is ready to use.</div>
          )}
        </div>
        {requests.some(row => row.status === 'applied') && (
          <button className="primary" disabled={running} onClick={onContinue}>
            <Wand2 size={14} /> Continue coding with approved packages
          </button>
        )}
      </div>
    );
  if (tab === 'visual')
    return (
      <div className="tool-pane upgrade-pane">
        <span className="eyebrow">BROWSER EVIDENCE</span>
        <h2>See what actually rendered.</h2>
        <p>
          Checks run in a fresh container on the app’s internal network. Only your preview origin is allowed;
          no host browser profile or credentials are used.
        </p>
        {project.profile === 'accounts' && (
          <div className="file-plan">
            <strong>Authenticated user journeys</strong>
            <p>
              Run all checks to test registration, verification, member records, viewer restrictions, admin
              pages, and logout in a disposable database at both screen sizes.
            </p>
            <button disabled={running} onClick={onValidate}>
              Run all checks and journeys
            </button>
            {project.journeys && !Array.isArray(project.journeys) && Array.isArray(project.journeys.checks) && (
              <>
                <p>
                  {project.journeys.status} ·{' '}
                  {project.journeys.source_digest === project.source_digest
                    ? 'current source'
                    : 'older source'}
                </p>
                {project.journeys.checks.map((row, i) => (
                  <p key={i}>
                    {row.status} · {row.name}
                  </p>
                ))}
                <small>{project.journeys.provider_checkout}</small>
              </>
            )}
            {Array.isArray(project.journeys) && project.journeys.length > 0 && (
              <div style={{ marginTop: '8px' }}>
                {project.journeys.map((j, i) => (
                  <div key={i} style={{ marginBottom: '6px' }}>
                    <strong>{j.name || `Journey ${i + 1}`}</strong>: {j.status || 'passed'}
                    {Array.isArray(j.checks) &&
                      j.checks.map((c, ci) => (
                        <p key={ci} style={{ margin: '2px 0 2px 12px' }}>
                          {c.status} · {c.name}
                        </p>
                      ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        <form
          className="visual-form"
          onSubmit={e => {
            e.preventDefault();
            let parsedActions = [];
            try {
              parsedActions = actions ? JSON.parse(actions) : [];
            } catch {
              parsedActions = [];
            }
            perform(() =>
              launch(`/projects/${project.id}/visual`, { path, viewport, actions: parsedActions }),
            );
          }}>
          <label>
            APP PATH
            <input
              required
              value={path}
              onChange={e => setPath(e.target.value)}
              placeholder="/"
              maxLength={1000}
            />
          </label>
          <label>
            VIEWPORT
            <select value={viewport} onChange={e => setViewport(e.target.value)}>
              <option value="desktop">Desktop · 1280 × 800</option>
              <option value="mobile">Mobile · 390 × 844</option>
            </select>
          </label>
          <details>
            <summary>Optional interaction checks</summary>
            <p>
              Up to 12 click, fill, or visible actions. Do not enter secrets; actions can change the preview
              database.
            </p>
            <textarea
              aria-label="Browser actions JSON"
              value={actions}
              onChange={e => setActions(e.target.value)}
              spellCheck={false}
            />
            <code>{'[{"action":"visible","selector":"h1","value":""}]'}</code>
          </details>
          <button className="primary" disabled={running}>
            <Camera size={14} /> Run browser check
          </button>
        </form>
        {item ? (
          <>
            <div className="evidence-tabs">
              {evidence.map(row => (
                <button
                  key={row.id}
                  className={item.id === row.id ? 'selected' : ''}
                  onClick={() => setSelected(row.id)}>
                  {row.viewport} · {row.status}
                  {row.source_digest !== project.source_digest ? ' · older source' : ''}
                </button>
              ))}
            </div>
            <Screenshot projectId={project.id} item={item} />
            <div className="evidence-detail">
              <strong>
                {item.title || 'Untitled page'} · {item.path}
              </strong>
              <p>
                {item.horizontal_overflow
                  ? 'Horizontal overflow detected.'
                  : 'No horizontal overflow detected.'}{' '}
                {item.actions?.length || 0} interaction checks completed.
              </p>
              {[...(item.errors || []), ...(item.failed_requests || [])].map((text, i) => (
                <pre key={i}>{text}</pre>
              ))}
            </div>
          </>
        ) : (
          <div className="backup-empty">
            Your desktop and mobile screenshots will appear here after a browser check.
          </div>
        )}
      </div>
    );
  if (tab === 'release')
    return (
      <div className="tool-pane upgrade-pane">
        <span className="eyebrow">SELF-HOSTED RELEASE</span>
        <h2>Take your app beyond the preview.</h2>
        <p>
          Export the validated source with a static React server, production FastAPI process, database
          migrations, and isolated PostgreSQL. No cloud account is touched.
        </p>
        {project.profile === 'accounts' && (
          <div className="release-warning">
            <ShieldCheck size={18} />
            <p>
              <strong>Accounts & billing starter</strong>
              <br />
              For administrator access, open the project source folder in Terminal and run{' '}
              <code>
                docker compose -f ../runtime.json exec api python -m app.manage create-admin --email
                you@example.com
              </code>
              . The command asks for your password privately.
            </p>
          </div>
        )}
        <div className="release-steps">
          <article>
            <span>01</span>
            <div>
              <strong>Validate this exact version</strong>
              <p>
                {validated
                  ? 'Current source passed its configured checks.'
                  : 'Run the checks first. Source changes invalidate the previous result.'}
              </p>
              <button disabled={running} onClick={onValidate}>
                <Play size={13} /> Run checks
              </button>
            </div>
          </article>
          <article>
            <span>02</span>
            <div>
              <strong>Review the release</strong>
              <p>
                Uses cached runtime images on your computer. Includes build scripts and a deployment
                checklist; excludes passwords, preview data, chat, and local documents.
              </p>
            </div>
          </article>
          <article>
            <span>03</span>
            <div>
              <strong>Build and start explicitly</strong>
              <p>
                Extract the ZIP, run <code>bash build-release.sh</code>, then{' '}
                <code>docker compose up -d --wait</code>. The default address is loopback-only.
              </p>
            </div>
          </article>
        </div>
        <div className="release-warning">
          <ShieldCheck size={18} />
          <p>
            {project.profile === 'accounts'
              ? 'Includes HTTPS, role enforcement, Stripe Checkout, email/webhook delivery, and private monitoring. Follow DEPLOY.md to configure your server and accounts; test with provider sandbox credentials before enabling live payments.'
              : 'The simple starter has anonymous records. Create an Accounts & billing project and port your app before using the public deployment kit.'}
          </p>
        </div>
        <label className="check-option">
          <input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} />
          <span>
            I reviewed the release scope and deployment checklist
            <small>Source fingerprint: {(project.source_digest || '').slice(0, 16)}…</small>
          </span>
        </label>
        <button
          className="primary"
          disabled={running || !validated || !reviewed}
          onClick={() => perform(() => downloadRelease(project))}>
          <Download size={15} /> Download reviewed release
        </button>
      </div>
    );
  return null;
}
