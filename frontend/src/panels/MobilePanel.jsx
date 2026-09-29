import { useEffect, useRef, useState } from 'react';
import { Download, Loader2, Play, RefreshCw, Smartphone, Square } from 'lucide-react';
import { downloadMobile, request } from '../api';
import { date } from '../format';
import './mobile.css';

export function MobileView({
  project,
  config,
  running,
  capabilities,
  builds,
  values,
  setValues,
  loading,
  error,
  log,
  starting,
  downloading,
  start,
  refresh,
  cancel,
  download,
  showLog,
}) {
  const field = (key, value) => setValues({ ...values, [key]: value });
  const ready =
    values.origin.trim() &&
    values.name.trim() &&
    values.app_id.trim() &&
    /^\d+\.\d+\.\d+$/.test(values.version) &&
    Number.isInteger(Number(values.build_number)) &&
    Number(values.build_number) > 0;
  const active = builds.some(item => item.status === 'running');
  const disabled = running || active || starting || !ready || !values.allow_network || config.offline_only;
  return (
    <div className="tool-pane mobile-pane">
      <div className="mobile-heading">
        <div>
          <span className="eyebrow">MOBILE BUILDS</span>
          <h2>From your app to your phone.</h2>
        </div>
        <button onClick={refresh} disabled={loading} aria-label="Refresh mobile tools and builds">
          <RefreshCw size={15} />
        </button>
      </div>
      <p>
        Package your deployed HTTPS app as an experimental mobile wrapper. Publish website changes before
        rebuilding; your backend stays hosted.
      </p>
      <div className="mobile-info">
        APK is debug-signed for sideloaded testing and cannot be published. AAB is signed with your own upload
        key and is what Google Play accepts. IPA uses your Mac’s Xcode signing setup. These builds need a
        connection and still need testing on a device.
      </div>
      {config.offline_only && (
        <p className="mobile-error" role="status">
          Offline-only mode is on. Mobile compilation is unavailable because it downloads native dependencies.
          Existing artifacts remain downloadable.
        </p>
      )}
      {error && (
        <p className="mobile-error" role="alert">
          {error}
        </p>
      )}
      <fieldset disabled={running || active || starting} className="mobile-fields">
        <legend>App details</legend>
        <label className="mobile-wide">
          Deployed app URL
          <input
            type="url"
            placeholder="https://app.example.com"
            value={values.origin}
            onChange={e => field('origin', e.target.value)}
          />
        </label>
        <label>
          App name
          <input maxLength={30} value={values.name} onChange={e => field('name', e.target.value)} />
        </label>
        <label>
          App ID
          <input
            placeholder="com.example.myapp"
            maxLength={155}
            value={values.app_id}
            onChange={e => field('app_id', e.target.value)}
          />
        </label>
        <label>
          Version
          <input
            placeholder="1.0.0"
            value={values.version}
            onChange={e => field('version', e.target.value)}
          />
        </label>
        <label>
          Build number
          <input
            type="number"
            min="1"
            max="2147483647"
            value={values.build_number}
            onChange={e => field('build_number', e.target.value)}
          />
        </label>
        <label>
          Apple Team ID <span>(IPA only)</span>
          <input
            placeholder="ABCDEFGHIJ"
            maxLength={10}
            value={values.team_id}
            onChange={e => field('team_id', e.target.value.toUpperCase())}
          />
        </label>
        <label>
          IPA distribution
          <select value={values.export_method} onChange={e => field('export_method', e.target.value)}>
            <option value="debugging">Development devices</option>
            <option value="release-testing">Registered test devices</option>
            <option value="app-store-connect">App Store Connect export</option>
          </select>
        </label>
        <label className="mobile-wide">
          App icon <span>(optional)</span>
          <input
            placeholder="/Users/you/brand/logo.png"
            spellCheck="false"
            autoComplete="off"
            value={values.icon_source ?? ''}
            onChange={e => field('icon_source', e.target.value)}
          />
          <small>
            Full path to a square PNG, 1024×1024 recommended. Without one the build ships Capacitor’s
            placeholder logo, which both stores reject.
          </small>
        </label>
        <label>
          Icon background
          <input
            placeholder="#FFFFFF"
            maxLength={7}
            spellCheck="false"
            value={values.icon_background ?? ''}
            onChange={e => field('icon_background', e.target.value)}
          />
          <small>Used behind adaptive icons, splash screens and the opaque iOS icon.</small>
        </label>
        <label className="mobile-wide">
          Upload keystore <span>(AAB only)</span>
          <input
            placeholder="/Users/you/keys/upload.jks"
            spellCheck="false"
            autoComplete="off"
            value={values.keystore_path ?? ''}
            onChange={e => field('keystore_path', e.target.value)}
          />
          <small>
            Full path to the .jks or .p12 holding your Play upload key. The file is read during the build and
            never copied or uploaded.
          </small>
        </label>
        <label>
          Key alias <span>(AAB only)</span>
          <input
            placeholder="upload"
            maxLength={64}
            spellCheck="false"
            autoComplete="off"
            value={values.key_alias ?? ''}
            onChange={e => field('key_alias', e.target.value)}
          />
        </label>
        <label>
          Keystore password
          <input
            type="password"
            maxLength={200}
            autoComplete="new-password"
            value={values.store_password ?? ''}
            onChange={e => field('store_password', e.target.value)}
          />
        </label>
        <label>
          Key password <span>(if different)</span>
          <input
            type="password"
            maxLength={200}
            autoComplete="new-password"
            value={values.key_password ?? ''}
            onChange={e => field('key_password', e.target.value)}
          />
          <small>Passwords are used for this build only. They are never saved or written to the log.</small>
        </label>
      </fieldset>
      <label className="check-option mobile-consent">
        <input
          type="checkbox"
          disabled={config.offline_only || running || active || starting}
          checked={values.allow_network && !config.offline_only}
          onChange={e => field('allow_network', e.target.checked)}
        />
        <span>
          Allow mobile tool downloads and native compilation on this computer.
          <small>
            IPA builds may update provisioning through your configured Xcode account. Exporting does not
            submit the app to a store.
          </small>
        </span>
      </label>
      <div className="mobile-targets">
        {['apk', 'aab', 'ipa'].map(target => {
          const info = capabilities?.[target];
          const isAvailable = typeof info === 'boolean' ? info : Boolean(info?.available);
          const blockers = Array.isArray(info?.blockers)
            ? info.blockers
            : typeof info?.blockers === 'string'
              ? [info.blockers]
              : [];
          const signingMissing =
            (target === 'ipa' && !/^[A-Z0-9]{10}$/.test(values.team_id)) ||
            (target === 'aab' &&
              !(values.keystore_path?.trim() && values.key_alias?.trim() && values.store_password));
          return (
            <article key={target} className="mobile-target">
              <Smartphone size={22} />
              <h3>{TITLES[target]}</h3>
              <p>
                {!info
                  ? 'Checking build tools…'
                  : isAvailable
                    ? DESCRIPTIONS[target]
                    : blockers.length
                      ? blockers.join(' ')
                      : 'Build tools not configured on this host.'}
              </p>
              <button
                className="primary"
                disabled={disabled || !isAvailable || signingMissing}
                onClick={() => start(target)}>
                {starting === target ? <Loader2 size={14} className="spin" /> : <Play size={14} />}Build {target.toUpperCase()}
              </button>
              {isAvailable && signingMissing && (
                <small>
                  {target === 'ipa'
                    ? 'Enter an Apple Team ID to enable IPA builds.'
                    : 'Enter the keystore path, alias and password to enable bundle builds.'}
                </small>
              )}
            </article>
          );
        })}
      </div>
      <div className="mobile-history" aria-live="polite">
        <h3>Builds &amp; downloads</h3>
        {!builds.length && (
          <p>Your builds will appear here with progress, logs, and a download when ready.</p>
        )}
        {builds.map(item => (
          <article className="mobile-build" key={item.id}>
            <div className="mobile-build-heading">
              <strong>
                {item.target.toUpperCase()} · {item.version} ({item.build_number})
              </strong>
              <span className="plan-status">{item.status}</span>
            </div>
            <small>
              {date(item.created_at)} · {item.origin}
            </small>
            <p>{item.phase}</p>
            <div className="mobile-actions">
              {item.status === 'running' && (
                <button onClick={() => cancel(item)}>
                  <Square size={13} />
                  Cancel build
                </button>
              )}
              <button onClick={() => showLog(item)}>View build log</button>
              {item.status === 'completed' && (
                <button disabled={downloading === item.id} onClick={() => download(item)}>
                  <Download size={14} />
                  {downloading === item.id ? 'Downloading…' : `Download ${item.target.toUpperCase()}`}
                </button>
              )}
            </div>
            {item.sha256 && (
              <details>
                <summary>Artifact details</summary>
                <p>
                  {(item.bytes / 1024 / 1024).toFixed(1)} MiB · {item.filename}
                </p>
                <code>SHA-256: {item.sha256}</code>
              </details>
            )}
          </article>
        ))}
      </div>
      {log !== null && (
        <section className="mobile-log">
          <h3>Build log</h3>
          <pre tabIndex={0}>{log || 'No command output yet.'}</pre>
        </section>
      )}
    </div>
  );
}

const TITLES = { apk: 'Android APK', aab: 'Play app bundle', ipa: 'iOS IPA' };
const DESCRIPTIONS = {
  apk: 'Android tools detected. Produces a debug-signed testing APK for sideloading, not for Play.',
  aab: 'Android tools detected. Produces an .aab signed with your upload key, which is what Google Play accepts.',
  ipa: 'Xcode detected. Configure signing for this app ID before building.',
};

export default function MobilePanel({ project, config, running, perform, launch }) {
  const [capabilities, setCapabilities] = useState(null);
  const [builds, setBuilds] = useState([]);
  const defaultOrigin = project.preview_url
    ? project.preview_url.startsWith('http')
      ? project.preview_url
      : window.location.origin + project.preview_url
    : window.location.origin;
  const cleanName = project.name.toLowerCase().replace(/[^a-z0-9]/g, '') || 'app';
  const [values, setValues] = useState({
    origin: defaultOrigin,
    name: project.name.slice(0, 30),
    app_id: `com.foundry.${cleanName}`,
    version: '1.0.0',
    build_number: '1',
    team_id: '',
    export_method: 'debugging',
    icon_source: '',
    icon_background: '#FFFFFF',
    keystore_path: '',
    key_alias: '',
    store_password: '',
    key_password: '',
    allow_network: !config?.offline_only,
  });
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState('');
  const [downloading, setDownloading] = useState('');
  const [error, setError] = useState('');
  const [log, setLog] = useState(null);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  async function refresh() {
    setLoading(true);
    try {
      const [tools, history] = await Promise.all([
        request('/mobile/capabilities'),
        request(`/projects/${project.id}/mobile/builds`),
      ]);
      if (alive.current) {
        setCapabilities(tools);
        setBuilds(history);
        setError('');
      }
    } catch (e) {
      if (alive.current) setError(e.message);
    } finally {
      if (alive.current) setLoading(false);
    }
  }
  useEffect(() => {
    refresh();
  }, [project.id, config.offline_only]);
  useEffect(() => {
    let stopped = false,
      timer;
    async function poll() {
      try {
        const rows = await request(`/projects/${project.id}/mobile/builds`);
        if (!stopped) {
          setBuilds(rows);
          if (running || rows.some(row => row.status === 'running')) timer = setTimeout(poll, 1500);
        }
      } catch (e) {
        if (!stopped) {
          setError(e.message);
          timer = setTimeout(poll, 3000);
        }
      }
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [project.id, running]);
  async function start(target) {
    setStarting(target);
    setError('');
    setLog(null);
    try {
      await launch(`/projects/${project.id}/mobile/builds`, {
        ...values,
        target,
        build_number: Number(values.build_number),
        source_digest: project.source_digest,
      });
      await refresh();
    } catch (e) {
      if (alive.current) setError(e.message);
    } finally {
      if (alive.current) setStarting('');
    }
  }
  async function download(item) {
    setDownloading(item.id);
    try {
      await downloadMobile(project.id, item);
    } catch (e) {
      if (alive.current) setError(e.message);
    } finally {
      if (alive.current) setDownloading('');
    }
  }
  return (
    <MobileView
      {...{
        project,
        config,
        running,
        capabilities,
        builds,
        values,
        setValues,
        loading,
        error,
        log,
        starting,
        downloading,
        start,
        refresh,
        download,
      }}
      cancel={item =>
        perform(async () => {
          await request(`/runs/${item.id}/cancel`, {});
        })
      }
      showLog={item =>
        perform(async () => {
          const result = await request(`/projects/${project.id}/mobile/builds/${item.id}/log`);
          if (alive.current) setLog(result.log);
        })
      }
    />
  );
}
