import {useEffect, useRef, useState} from 'react';
import './style.css';

const fragment = new URLSearchParams(window.location.hash.slice(1));
const initialAction = ['verify', 'reset', 'invite'].includes(fragment.get('action')) ? {kind: fragment.get('action'), token: fragment.get('token')} : null;
if (initialAction) window.history.replaceState(null, '', window.location.pathname);
const price = (amount, currency) => {
  const format = new Intl.NumberFormat(undefined, {style: 'currency', currency});
  return format.format(amount / 10 ** format.resolvedOptions().maximumFractionDigits);
};
const when = value => new Date(value * 1000).toLocaleString();

export default function App() {
  const [config, setConfig] = useState(null), [account, setAccount] = useState(null), [csrf, setCsrf] = useState('');
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [view, setView] = useState('workspace'), [authMode, setAuthMode] = useState('login'), [action, setAction] = useState(initialAction);
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [previewLink, setPreviewLink] = useState('');
  const [notes, setNotes] = useState([]), [text, setText] = useState(''), [users, setUsers] = useState([]), [inviteEmail, setInviteEmail] = useState('');
  const [billing, setBilling] = useState({products: [], mode: 'off'}), [orders, setOrders] = useState([]), [ops, setOps] = useState(null);
  const checkoutKeys = useRef({});

  async function api(path, body, method) {
    const response = await fetch('/api' + path, {method: method || (body === undefined ? 'GET' : 'POST'), credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', ...(csrf ? {'X-CSRF-Token': csrf} : {})}, body: body === undefined ? undefined : JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401 && path !== '/auth/login') {setAccount(null); setCsrf('');}
      throw new Error(typeof data.detail === 'string' ? data.detail : 'The request could not be completed.');
    }
    return data;
  }
  async function perform(work) {
    setBusy(true); setError(''); setNotice(''); setPreviewLink('');
    try {await work();} catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  async function refresh(tab = view) {
    if (tab === 'workspace') setNotes(await api('/notes'));
    if (tab === 'billing') {const [products, history] = await Promise.all([api('/billing/products'), api('/billing/orders')]); setBilling(products); setOrders(history);}
    if (tab === 'people') setUsers(await api('/admin/users'));
    if (tab === 'operations') setOps(await api('/admin/ops'));
  }
  useEffect(() => {
    let active = true;
    async function start() {
      try {
        const response = await fetch('/api/config'); if (!response.ok) throw new Error('Application is not ready.');
        const settings = await response.json(); if (active) setConfig(settings);
        const me = await fetch('/api/auth/session', {credentials: 'same-origin'});
        if (me.ok) {const data = await me.json(); if (active) {setAccount(data.user); setCsrf(data.csrf);}}
      } catch (e) {if (active) setError(e.message);} finally {if (active) setLoading(false);}
    }
    start(); return () => {active = false;};
  }, []);
  useEffect(() => {if (account) perform(() => refresh(view));}, [account?.id, view]);

  async function submitAuth(e) {
    e.preventDefault();
    await perform(async () => {
      if (action) {
        const data = await api('/auth/complete/' + action.kind, {token: action.token || '', password});
        setAction(null); setPassword(''); setAuthMode('login'); setAccount(null); setCsrf(''); setNotice(data.message); return;
      }
      if (authMode === 'login') {
        const data = await api('/auth/login', {email, password});
        setPassword(''); setAccount(data.user); setCsrf(data.csrf); setView('workspace');
      } else {
        const data = await api(authMode === 'register' ? '/auth/register' : '/auth/request-reset', authMode === 'register' ? {email, password} : {email});
        setNotice(data.message); setPreviewLink(data.preview_link || ''); setPassword('');
      }
    });
  }
  const messages = <>{error && <div className="message error" role="alert">{error}</div>}{notice && <div className="message" role="status">{notice}</div>}{previewLink && <div className="message"><strong>Local preview email</strong><p>Email is disabled in preview. Open this temporary link to complete the flow.</p><button onClick={() => {const params = new URLSearchParams(previewLink.split('#')[1]); setAction({kind: params.get('action'), token: params.get('token')}); setPreviewLink(''); setAccount(null); setCsrf('');}}>Open account link</button></div>}</>;
  if (loading) return <main className="loading"><span className="brand-mark">f</span><p>Opening your workspace…</p></main>;
  if (!account || action) return <main className="auth-layout">
    <section className="auth-story"><a className="brand" href="/">foundry<span>workspace</span></a><div><span className="eyebrow">A PLACE FOR YOUR NEXT CHAPTER</span><h1>Good work<br/>starts here.</h1><p>Your ideas, a private workspace, and room to grow.</p><div className="story-cards"><article><span>01</span><strong>Make it yours.</strong><p>Keep your work in your own account.</p></article><article><span>02</span><strong>Bring your people.</strong><p>Give each person the access they need.</p></article></div></div><small>Built with Local Foundry</small></section>
    <section className="auth-panel"><div className="auth-card"><span className="eyebrow">{config?.environment === 'preview' ? 'LOCAL PREVIEW' : 'YOUR WORKSPACE'}</span><h2>{action ? action.kind === 'verify' ? 'Verify your email.' : 'Set your password.' : authMode === 'login' ? 'Welcome back.' : authMode === 'register' ? 'Make yourself at home.' : 'A fresh start.'}</h2><p>{action ? 'Complete this account request to continue.' : authMode === 'login' ? 'Sign in to pick up where you left off.' : authMode === 'register' ? 'Create an account. We’ll send a verification link.' : 'Enter your email for a password reset link.'}</p>{messages}
    <form onSubmit={submitAuth}>{!action && <label>Email address<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)}/></label>}{((!action && authMode !== 'reset') || (action && action.kind !== 'verify')) && <label>{action ? 'New password' : 'Password'}<input type="password" autoComplete={!action && authMode === 'login' ? 'current-password' : 'new-password'} minLength={!action && authMode === 'login' ? 1 : 12} maxLength={128} required value={password} onChange={e => setPassword(e.target.value)}/>{(action || authMode === 'register') && <small>Use at least 12 characters.</small>}</label>}<button className="primary wide" disabled={busy || !config}>{busy ? 'Please wait…' : action ? 'Complete account request' : authMode === 'login' ? 'Sign in →' : authMode === 'register' ? 'Create account →' : 'Send reset link →'}</button></form>
    <div className="auth-links">{authMode === 'login' && !action && <button onClick={() => setAuthMode('reset')}>Forgot your password?</button>}{config?.signup && authMode === 'login' && !action && <button onClick={() => setAuthMode('register')}>Create an account</button>}{(authMode !== 'login' || action) && <button onClick={() => {setAction(null); setAuthMode('login'); setError('');}}>Back to sign in</button>}</div>{config && !config.signup && <p className="muted small">New here? Ask your administrator for an invitation.</p>}</div></section>
  </main>;
  const tabs = [['workspace', 'My workspace', '◈'], ['billing', 'Billing', '◉'], ...(account.role === 'admin' ? [['people', 'People & access', '◎'], ['operations', 'Operations', '▤']] : [])];
  return <div className="app-shell"><aside className="sidebar"><a className="brand" href="/">foundry<span>workspace</span></a><div className="workspace-label"><span className="brand-mark">f</span><div>Personal workspace<small>{config?.environment === 'production' ? 'Live application' : 'Local preview'}</small></div></div><nav aria-label="Main navigation">{tabs.map(([key, title, icon]) => <button key={key} className={view === key ? 'selected' : ''} onClick={() => setView(key)}><span aria-hidden="true">{icon}</span>{title}</button>)}</nav><div className="account"><div className="avatar">{account.email[0].toUpperCase()}</div><div><strong>{account.email}</strong><small>{account.role}</small></div><button aria-label="Sign out" disabled={busy} onClick={() => perform(async () => {await api('/auth/logout', {}); setAccount(null); setCsrf(''); checkoutKeys.current = {};})}>↗</button></div></aside>
  <main className="content"><header><div><span className="eyebrow">YOUR SPACE TO BUILD</span><h1>{tabs.find(t => t[0] === view)?.[1]}</h1></div><button disabled={busy} onClick={() => perform(() => refresh())}>↻ Refresh</button></header>{messages}
  {view === 'workspace' && <><section className="hero"><div><span className="tag">PRIVATE TO YOU</span><h2>A little space.<br/>A lot of possibility.</h2><p>Capture a thought, sketch a plan, or start something new.</p></div><div className="hero-art" aria-hidden="true"><i/><i/><i/><span>✳</span></div></section><div className="section-title"><h2>Your notes <span>{notes.length}</span></h2><small>Only you can see these notes.</small></div>{account.role === 'viewer' ? <div className="message">Your viewer role can read existing notes. Ask an administrator for editing access.</div> : <form className="note-form" onSubmit={e => {e.preventDefault(); perform(async () => {await api('/notes', {text}); setText(''); await refresh();});}}><input aria-label="New note" placeholder="What’s on your mind?" maxLength={4000} required value={text} onChange={e => setText(e.target.value)}/><button className="primary" disabled={busy || !text.trim()}>+ Add note</button></form>}<div className="notes">{notes.map(note => <article key={note.id}><p>{note.text}</p><footer><small>{when(note.created_at)}</small>{account.role !== 'viewer' && <button disabled={busy} aria-label="Delete note" onClick={() => perform(async () => {await api('/notes/' + note.id, undefined, 'DELETE'); await refresh();})}>Delete</button>}</footer></article>)}</div>{!notes.length && <div className="empty"><span>✳</span><h3>Your next idea belongs here.</h3><p>Add your first note to get started.</p></div>}</>}
  {view === 'billing' && <><div className="section-title"><div><h2>Simple, secure checkout.</h2><p>Payments are completed on Stripe’s hosted checkout.</p></div><span className="tag">{billing.mode === 'off' ? 'PAYMENTS OFF' : billing.mode.toUpperCase() + ' MODE'}</span></div>{billing.mode === 'off' && <div className="message">Payments are disabled in this environment. No checkout can charge a card here.</div>}<div className="products">{billing.products.map(product => <article key={product.id}><span className="eyebrow">ONE-TIME PURCHASE</span><h2>{product.name}</h2><strong className="price">{price(product.amount, product.currency)}</strong><button className="primary wide" disabled={busy || billing.mode === 'off' || account.role === 'viewer'} onClick={() => perform(async () => {const requestId = checkoutKeys.current[product.id] ||= crypto.randomUUID(); const result = await api('/billing/checkout', {product: product.id, request_id: requestId}); window.location.assign(result.url);})}>Continue to checkout →</button></article>)}</div>{!billing.products.length && <div className="empty"><h3>No products published yet.</h3><p>Available purchases will appear here.</p></div>}<div className="section-title"><h2>Purchase history</h2><small>Updated after payment confirmation.</small></div><div className="table-wrap"><table><thead><tr><th>Product</th><th>Amount</th><th>Status</th><th>Date</th></tr></thead><tbody>{orders.map(order => <tr key={order.id}><td>{order.product}</td><td>{price(order.amount-order.refunded, order.currency)}</td><td><span className="tag">{order.status.replaceAll('_', ' ')}</span></td><td>{when(order.created_at)}</td></tr>)}</tbody></table>{!orders.length && <p className="table-empty">No purchases yet.</p>}</div></>}
  {view === 'people' && <><section className="panel"><h2>A place for your people.</h2><p>Invite a member, then choose their role. Changing access signs them out.</p><form className="note-form" onSubmit={e => {e.preventDefault(); perform(async () => {const result = await api('/admin/invite', {email: inviteEmail}); setNotice(result.message); setPreviewLink(result.preview_link || ''); setInviteEmail(''); await refresh();});}}><input type="email" aria-label="Invite email address" placeholder="colleague@example.com" required value={inviteEmail} onChange={e => setInviteEmail(e.target.value)}/><button className="primary" disabled={busy}>Send invitation</button></form></section><div className="role-guide"><article><strong>Administrator</strong><p>Manages people, deliveries, and operations.</p></article><article><strong>Member</strong><p>Creates private notes and makes purchases.</p></article><article><strong>Viewer</strong><p>Reads their own records and purchase history.</p></article></div><div className="table-wrap"><table><thead><tr><th>Person</th><th>Status</th><th>Role</th><th>Access</th></tr></thead><tbody>{users.map(user => <tr key={user.id}><td>{user.email}{user.id === account.id && <small> (you)</small>}</td><td>{!user.active ? 'Disabled' : user.verified ? 'Verified' : 'Invited / unverified'}</td><td><select aria-label={'Role for ' + user.email} value={user.role} disabled={busy} onChange={e => perform(async () => {await api('/admin/users/' + user.id, {role: e.target.value, active: !!user.active}, 'PATCH'); if (user.id === account.id) {setAccount(null); setCsrf('');} else await refresh();})}>{['viewer','member','admin'].map(role => <option key={role}>{role}</option>)}</select></td><td><button disabled={busy} onClick={() => perform(async () => {await api('/admin/users/' + user.id, {role: user.role, active: !user.active}, 'PATCH'); if (user.id === account.id) {setAccount(null); setCsrf('');} else await refresh();})}>{user.active ? 'Disable' : 'Enable'}</button></td></tr>)}</tbody></table></div></>}
  {view === 'operations' && ops && <><div className="stats"><article><span>Requests</span><strong>{ops.metrics.reduce((n, row) => n+row.count, 0).toLocaleString()}</strong><small>Since metrics were initialized</small></article><article><span>Server errors</span><strong>{ops.metrics.filter(row => row.status >= 500).reduce((n, row) => n+row.count, 0)}</strong><small>Inspect server logs by request ID</small></article><article><span>Delivery worker</span><strong>{ops.worker && Date.now()/1000-ops.worker.heartbeat < 120 ? 'Healthy' : 'Waiting'}</strong><small>{ops.integrations.enabled ? 'Integrations enabled' : 'Integrations disabled'}</small></article></div><section className="panel"><h2>Connected services</h2><div className="service-list"><div><strong>Stripe</strong><span className="tag">{ops.payment_mode}</span></div><div><strong>Transactional email</strong><span className="tag">{ops.integrations.email ? 'Configured' : 'Off'}</span></div><div><strong>Outgoing webhook</strong><span className="tag">{ops.integrations.webhook ? 'Configured' : 'Off'}</span></div></div><p className="muted small">Service credentials are managed by the deployment operator.</p></section><div className="section-title"><h2>Delivery queue</h2></div><div className="table-wrap"><table><thead><tr><th>Kind</th><th>Status</th><th>Attempts</th><th>Last result</th><th/></tr></thead><tbody>{ops.deliveries.map(row => <tr key={row.id}><td>{row.kind}</td><td>{row.status}</td><td>{row.attempts}</td><td>{row.last_error || '—'}</td><td>{row.status === 'dead' && <button disabled={busy} onClick={() => perform(async () => {await api('/admin/deliveries/' + row.id + '/retry', {}); await refresh();})}>Retry</button>}</td></tr>)}</tbody></table>{!ops.deliveries.length && <p className="table-empty">No deliveries queued.</p>}</div><div className="section-title"><h2>Monitoring alerts</h2></div>{ops.alerts.length ? ops.alerts.map(row => <div className="message" key={row.id}>{row.name} · {row.status} · {when(row.created_at)}</div>) : <p className="muted">No recorded alerts. External monitoring must be enabled in the deployment.</p>}<div className="section-title"><h2>Audit activity</h2><small>Most recent 100 events</small></div><div className="table-wrap"><table><thead><tr><th>Event</th><th>Actor</th><th>When</th></tr></thead><tbody>{ops.audit.map(row => <tr key={row.id}><td>{row.action}</td><td><code>{row.actor.slice(0, 12)}</code></td><td>{when(row.created_at)}</td></tr>)}</tbody></table></div></>}
  <footer className="page-footer">A little structure. More room to create.<span>Built with Local Foundry</span></footer></main></div>;
}
