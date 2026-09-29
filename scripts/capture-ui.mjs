#!/usr/bin/env node
/** Capture every primary Local Foundry UI state with installed Google Chrome.
 *
 * The script serves the production bundle with a deterministic in-memory API.
 * It never reads .env, provider keys, GitHub credentials, or real project data.
 * No npm browser package is required; Node talks directly to Chrome DevTools.
 */
import {spawn, spawnSync} from 'node:child_process';
import {createServer} from 'node:http';
import {cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {extname, join, resolve, sep} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const accountsMode = process.argv.includes('--accounts');
const windowsFixture = process.env.FOUNDRY_CAPTURE_PLATFORM === 'windows';
const fixturePlatform = windowsFixture
  ? {system:'Linux', release:'WSL2 fixture', machine:'x86_64', python:'3.12', label:'Windows / WSL2', wsl:true, wsl2:true}
  : {system:'Darwin', release:'15.6', machine:'arm64', python:'3.12', label:'macOS', wsl:false, wsl2:false};
// Accessibility scanning is on by default because a state nobody scans is a state
// nobody checks. --no-a11y captures screenshots only.
const scanAccessibility = !process.argv.includes('--no-a11y');
// Serious and critical findings fail the run. Minor and moderate are recorded but
// do not fail, so the gate stays actionable instead of becoming noise to mute.
const FAILING_IMPACTS = new Set(['serious', 'critical']);
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const accessibilityFindings = [];
// Known findings that pre-date this gate are recorded in a baseline so the gate
// fails on NEW regressions rather than on accumulated debt. A gate that is red
// from the first run gets muted; one that is green until you break something
// does not. --a11y-baseline rewrites the file after a deliberate fix.
const updateBaseline = process.argv.includes('--a11y-baseline');
const baselinePath = join(root, 'screenshots', accountsMode ? 'a11y-baseline.accounts.json' : 'a11y-baseline.builder.json');
const accountsBuild = accountsMode ? await mkdtemp(join(tmpdir(), 'foundry-accounts-ui-')) : null;
const dist = join(accountsBuild || join(root, 'frontend'), 'dist');
const output = join(root, 'screenshots', accountsMode ? 'accounts' : 'ui');
const projectId = 'a'.repeat(32);
const runId = 'c'.repeat(32);
const now = '2026-09-16T12:00:00+00:00';
const state = {project: false, active: false, offline: false};
const accountsState = {signedIn: false, role: 'admin', empty: false, mode: 'test'};

function accountFixture(request, response, path) {
  const stamp = Date.parse('2026-09-18T10:30:00Z')/1000;
  const user = {id:'fixture-owner',email:'alex@example.com',role:accountsState.role,verified:1,active:1};
  if (path === '/api/config') return json(response, {environment:'preview',signup:true,payments:accountsState.mode});
  if (path === '/api/auth/session') return json(response, accountsState.signedIn ? {user,csrf:'fixture-csrf'} : {user:null,csrf:''});
  if (path === '/api/notes') return json(response, accountsState.empty ? [] : [
    {id:'n1',text:'A calmer place to plan the next release. Start with the essentials, then make room for the details.',created_at:stamp-3600},
    {id:'n2',text:'Friday: share the first draft with the team and collect their feedback.',created_at:stamp-7200}]);
  if (path === '/api/billing/products') return json(response,{mode:accountsState.mode,products:[{id:'starter',name:'Starter access',amount:1900,currency:'usd'},{id:'studio',name:'Studio access',amount:4900,currency:'usd'}]});
  if (path === '/api/billing/orders') return json(response,[{id:'order1',product:'starter',amount:1900,currency:'usd',status:'paid',refunded:0,created_at:stamp-86400}]);
  if (path === '/api/admin/users') return json(response,[user,{id:'fixture-member',email:'sam@example.com',role:'member',verified:1,active:1},{id:'fixture-viewer',email:'lee@example.com',role:'viewer',verified:0,active:1}]);
  if (path === '/api/admin/ops') return json(response,{environment:'preview',payment_mode:'test',integrations:{enabled:true,email:true,webhook:true},worker:{heartbeat:stamp},
    metrics:[{route:'/api/notes',method:'GET',status:200,count:1248,duration_ms:88000},{route:'/api/notes',method:'POST',status:500,count:2,duration_ms:1000}],
    audit:[{id:'event1',actor:'fixture-owner',action:'account.invite',target:'fixture-member',created_at:stamp-120},{id:'event2',actor:'stripe',action:'order.paid',target:'order1',created_at:stamp-450}],
    deliveries:[{id:'delivery1',kind:'email',status:'sent',attempts:1,last_error:'',created_at:stamp-120},{id:'delivery2',kind:'webhook',status:'dead',attempts:8,last_error:'provider_http_503',created_at:stamp-3600}],alerts:[{id:'alert1',name:'FailedDeliveries',status:'firing',created_at:stamp-300}]});
  return json(response,{detail:'No fixture for this action'},404);
}

const project = () => ({
  id: projectId,
  profile: 'accounts',
  name: 'Reading room',
  created_at: now,
  repo: 'alex/reading-room',
  preview_url: null,
  sync_state: {},
  source_digest: '5'.repeat(64),
  dependency_requests: [{id: '9'.repeat(32), status: 'pending', reason: 'Format dates in your reading journal.',
    packages: [{ecosystem: 'npm', name: 'date-fns', version: '4.1.0'}], source_digest: '5'.repeat(64), created_at: now}],
  visual_checks: [],
  context: {revision: 1, body: {requirements:'A private reading journal with searchable notes.', architecture:'React, FastAPI and PostgreSQL. Preserve server-side ownership.', data_model:'Users own their records.', decisions:'Keep previews disconnected.', open_questions:'Which reading statistics are most useful?'}, agent_notes:[{text:'Reading records are stored in PostgreSQL.', at:now}]},
  feature_plans: [{id:'6'.repeat(32), title:'A richer reading journal', status:'needs_review', created_at:now, updated_at:now,
    milestones:[{id:'m1', title:'Search notes', prompt:'Add search.', acceptance:'Filter notes and clear the filter.', status:'completed', result:'Search added and checked.'},
      {id:'m2', title:'Reading status', prompt:'Track reading status.', acceptance:'Status persists across reloads.', status:'needs_review'}],
    usage:{input_tokens:14200,output_tokens:3800,estimated_usd:0.092}, checkpoint:{phase:'tool_finished',tool:'patch_file'}}],
  messages: [
    {role: 'user', mode: 'coder', content: 'Build a calm personal reading list with status filters.', created_at: now},
    {role: 'assistant', mode: 'coder', content: 'Created the reading list and connected it to PostgreSQL.\n\nAll automatic checks passed.', created_at: now},
  ],
  versions: [
    {id: 'b'.repeat(32), label: 'After AI edit', digest: '1'.repeat(64), created_at: now},
    {id: 'd'.repeat(32), label: 'Starting template', digest: '2'.repeat(64), created_at: '2026-09-16T11:20:00+00:00'},
  ],
  backups: [
    {id: 'e'.repeat(32), label: 'Before validated migrations', bytes: 48128, sha256: '3'.repeat(64), created_at: now},
    {id: 'f'.repeat(32), label: 'Manual backup', bytes: 47002, sha256: '4'.repeat(64), created_at: '2026-09-16T11:40:00+00:00'},
  ],
  documents: {folder: '/Users/alex/Library/Application Support/Local Foundry/data/workspace/documents',
    indexed_files: 18, skipped_files: 1, chunks: 146, indexed_at: now, ocr_available: true},
  file_plans: [{id: '7'.repeat(32), prompt: 'Group invoices and meeting notes by kind.', status: 'planned',
    created_at: now, operations: [
      {op: 'mkdir', destination: 'Invoices'},
      {op: 'move', source: 'invoice-september.pdf', destination: 'Invoices/invoice-september.pdf'},
      {op: 'mkdir', destination: 'Meeting notes'},
      {op: 'move', source: 'team-sync.txt', destination: 'Meeting notes/team-sync.txt'},
    ]}],
  recovery_exports: [{id: '8'.repeat(32), filename: 'Reading-room-8f14a912.lfr',
    bytes: 7340032, sha256: '9'.repeat(64), created_at: now}],
  last_validation: {status: 'passed', gate_version:6, browser_checks:true, source_digest: '5'.repeat(64), created_at: now, checks: [
    {name: 'Python syntax', status: 'passed'},
    {name: 'React production build', status: 'passed'},
    {name: 'Database migrations in test database', status: 'passed'},
    {name: 'Backend tests', status: 'passed'},
    {name: 'Protected security contracts', status: 'passed'},
    {name: 'Authenticated user journeys', status: 'passed'},
    {name: 'Preview database backup', status: 'passed'},
    {name: 'Preview and database health', status: 'passed'},
  ]},
  active_run: state.active ? runId : null,
  active_run_kind: state.active ? 'build' : null,
});

const json = (response, value, status = 200) => {
  response.writeHead(status, {'content-type': 'application/json', 'cache-control': 'no-store'});
  response.end(JSON.stringify(value));
};

const mime = path => ({'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png'}[extname(path)] || 'application/octet-stream');

const server = createServer(async (request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  const path = url.pathname;
  if (accountsMode && path.startsWith('/api/')) return accountFixture(request, response, path);
  if (path === '/api/mobile/capabilities') return json(response, {
    apk: {available: !state.offline, blockers: state.offline ? ['Offline mode: native downloads unavailable.'] : []},
    aab: {available: !state.offline, blockers: state.offline ? ['Offline mode: native downloads unavailable.'] : []},
    ipa: {available: !windowsFixture && !state.offline, blockers: windowsFixture ? ['IPA builds require macOS with Xcode.'] : []}
  });
  if (path === `/api/projects/${projectId}/mobile/builds`) return json(response, [{
    id:'8'.repeat(32), target:'apk', status:'completed', phase:'Ready to download',
    name:'Reading room', origin:'https://reading.example.com', app_id:'com.example.readingroom',
    version:'1.0.0', build_number:1, created_at:now, bytes:5242880,
    filename:'com.example.readingroom-1.0.0-debug.apk', sha256:'d'.repeat(64)
  }]);
  if (path.endsWith('/mobile/builds/' + '8'.repeat(32) + '/log')) return json(response, {log:'UI fixture only. No native artifact was built by the screenshot runner.'});
  if (path === '/api/config') return json(response, {providers: {
    anthropic: {model: 'claude-sonnet-4-6', configured: true,
      limits: {budget_usd: 2, max_input_tokens: 180000, max_output_tokens: 24000,
        input_rate: 3, output_rate: 15, pricing_known: true}},
    openai: {model: 'gpt-5.4', configured: true,
      limits: {budget_usd: 2, max_input_tokens: 180000, max_output_tokens: 24000,
        input_rate: 2.5, output_rate: 15, pricing_known: true}},
    local: {model: 'qwen3-coder-local', configured: true,
      limits: {budget_usd: 0, max_input_tokens: 180000, max_output_tokens: 24000,
        input_rate: 0, output_rate: 0, pricing_known: true}},
  }, offline_only: state.offline, version: '0.10.1', runtime: fixturePlatform, local_vision: false,
  documents_folder: '/Users/alex/Library/Application Support/Local Foundry/data/workspace/documents',
  files_folder: '/Users/alex/Library/Application Support/Local Foundry/data/workspace/files',
  docker_installed: true, github_installed: true});
  if (path === '/api/diagnostics') return json(response, {
    platform: fixturePlatform,
    offline_only: state.offline, disk_free_bytes: 412 * 1024 * 1024 * 1024,
    offline_readiness: {ready: state.offline, blockers: []},
    checks: {
      python: {status: 'passed', detail: '3.12.11'}, node: {status: 'passed', detail: 'v22.18.0'},
      docker: {status: 'passed', detail: '28.3.3'}, compose: {status: 'passed', detail: '2.39.1'},
      github: {status: 'passed', detail: 'gh version 2.76.1'}, ocr: {status: 'passed', detail: 'tesseract 5.5.1'},
      builder_database: {status: 'passed', detail: 'connected'},
      web_image: {status: 'passed', detail: 'cached'}, api_image: {status: 'passed', detail: 'cached'},
      database_image: {status: 'passed', detail: 'cached'}, browser_image: {status: 'passed', detail: 'cached'},
      storage: {status: 'passed', detail: '/Users/alex/Library/Application Support/Local Foundry/data'},
      local_ai: {status: 'passed', detail: 'http://127.0.0.1:11434/v1 · HTTP 200'},
    },
  });
  if (path === '/api/projects') return json(response, state.project ? [project()] : []);
  if (path === `/api/projects/${projectId}`) return json(response, project());
  if (path === `/api/projects/${projectId}/files`) return json(response,
    ['backend/app/main.py', 'backend/migrations/001_notes.sql', 'frontend/src/App.jsx', 'frontend/src/style.css']);
  if (path === `/api/projects/${projectId}/file`) return json(response, {path: url.searchParams.get('path'),
    content: `export default function App() {\n  return <main><h1>My reading room</h1></main>;\n}\n`});
  if (path === `/api/projects/${projectId}/logs`) return json(response, {text:
    'api  | Database migrations are current.\napi  | Application startup complete.\nweb  | Vite ready on http://0.0.0.0:5173'});
  if (path === `/api/projects/${projectId}/documents/search`) return json(response, {results: [
    {citation: 'architecture/security-notes.md#chunk-4', path: 'architecture/security-notes.md', chunk: 4,
      snippet: 'The preview runs in isolated containers with read-only source mounts and no provider credentials.'},
    {citation: 'research/offline-checklist.pdf#chunk-11', path: 'research/offline-checklist.pdf', chunk: 11,
      snippet: 'Before disconnecting, cache model weights, Docker images, package dependencies, and recovery media.'},
  ]});
  if (path === `/api/projects/${projectId}/github/review`) return json(response, {
    repo: 'alex/reading-room', head: '6'.repeat(40), branch: 'main', source_digest: '5'.repeat(64),
    preserved_remote_files: 2, conflicts: [], changes: [
      {path: 'frontend/src/App.jsx', change: 'modified', truncated: false,
        diff: '--- before/frontend/src/App.jsx\n+++ after/frontend/src/App.jsx\n@@ -1 +1,3 @@\n-export default App\n+export default function App() {\n+  return <ReadingList />;\n+}\n'},
      {path: 'backend/migrations/002_books.sql', change: 'added', truncated: false,
        diff: '--- before/backend/migrations/002_books.sql\n+++ after/backend/migrations/002_books.sql\n@@ -0,0 +1 @@\n+CREATE TABLE books (...);\n'},
    ]});
  if (path === `/api/runs/${runId}`) {
    const after = Number(url.searchParams.get('after') || 0);
    return json(response, {id: runId, kind: 'build', status: 'running', more: false,
      events: after ? [] : [
        {id: 1, kind: 'tool', text: 'write_file · frontend/src/App.jsx'},
        {id: 2, kind: 'usage', text: '12,430 input · 1,218 output · about $0.0556'},
        {id: 3, kind: 'check', status: 'passed', text: 'React production build passed.'},
        {id: 4, kind: 'status', text: 'Running isolated backend tests…'},
      ]});
  }
  if (path.startsWith('/api/')) return json(response, {detail: `Unhandled fixture endpoint: ${path}`}, 404);

  let file = path === '/' ? join(dist, 'index.html') : resolve(dist, '.' + path);
  if (!file.startsWith(dist + sep) && file !== join(dist, 'index.html')) return json(response, {detail: 'Not found'}, 404);
  try {
    const body = await readFile(file);
    response.writeHead(200, {'content-type': mime(file), 'cache-control': 'no-store'});
    response.end(body);
  } catch {
    response.writeHead(404);
    response.end('Not found');
  }
});

function chromePath() {
  const candidates = [process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta',
    '/Applications/Chromium.app/Contents/MacOS/Chromium'];
  for (const path of candidates) if (path && existsSync(path)) return path;
  for (const name of ['google-chrome', 'chromium', 'chromium-browser']) {
    const result = spawnSync('which', [name], {encoding: 'utf8'});
    if (result.status === 0 && result.stdout.trim()) return result.stdout.trim();
  }
  throw new Error('Google Chrome was not found. Install Chrome or set CHROME_PATH, then rerun.');
}

function cdp(websocketUrl) {
  return new Promise((resolveConnection, rejectConnection) => {
    const socket = new WebSocket(websocketUrl);
    const pending = new Map();
    let nextId = 1;
    socket.addEventListener('open', () => resolveConnection({
      send(method, params = {}) {
        const id = nextId++;
        return new Promise((resolveCall, rejectCall) => {
          const timer = setTimeout(() => {pending.delete(id); rejectCall(new Error(`CDP timeout: ${method}`));}, 15000);
          pending.set(id, {resolveCall, rejectCall, timer});
          socket.send(JSON.stringify({id, method, params}));
        });
      },
      close() { socket.close(); },
    }));
    socket.addEventListener('error', event => rejectConnection(new Error('Could not connect to Chrome DevTools.')));
    socket.addEventListener('message', event => {
      const message = JSON.parse(String(event.data));
      if (!message.id || !pending.has(message.id)) return;
      const call = pending.get(message.id);
      clearTimeout(call.timer);
      pending.delete(message.id);
      if (message.error) call.rejectCall(new Error(message.error.message));
      else call.resolveCall(message.result);
    });
  });
}

async function waitFor(client, expression, timeout = 10000) {
  const deadline = Date.now() + timeout;
  let lastError = '';
  while (Date.now() < deadline) {
    const result = await client.send('Runtime.evaluate', {expression: `Boolean(${expression})`, returnByValue: true});
    if (result.result.value) return;
    if (result.exceptionDetails) lastError = result.exceptionDetails.exception?.description || result.exceptionDetails.text || '';
    await new Promise(resolveDelay => setTimeout(resolveDelay, 100));
  }
  // Report what the page actually showed. A bare "did not become ready" gives
  // whoever hits this in CI nothing to act on.
  const seen = await client.send('Runtime.evaluate', {returnByValue: true, expression: `(() => {
    const body = document.body;
    return {
      url: location.href,
      title: document.title,
      text: (body ? body.innerText : '').replace(/\\s+/g, ' ').trim().slice(0, 400),
      html: (body ? body.innerHTML : '').slice(0, 300),
      errors: (window.__captureErrors || []).slice(0, 5),
    };
  })()`}).then(result => result.result.value).catch(() => null);
  const detail = seen
    ? `\n  url: ${seen.url}\n  title: ${seen.title}\n  visible text: ${seen.text || '(none)'}\n  body html: ${seen.html || '(empty)'}` +
      (seen.errors?.length ? `\n  page errors:\n    ${seen.errors.join('\n    ')}` : '')
    : '\n  (page state could not be read)';
  throw new Error(`UI did not become ready: ${expression}` + (lastError ? `\n  last evaluation error: ${lastError.split('\n')[0]}` : '') + detail);
}

async function evaluate(client, expression) {
  const result = await client.send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text || 'Browser evaluation failed.');
  return result.result.value;
}

async function clickText(client, text, selector = 'button') {
  const value = JSON.stringify(text);
  const query = JSON.stringify(selector);
  const clicked = await evaluate(client, `(() => { const node = [...document.querySelectorAll(${query})].find(n => n.textContent.trim().includes(${value})); if (!node) return false; node.click(); return true; })()`);
  if (!clicked) throw new Error(`Could not find ${selector} containing “${text}”.`);
}

/** Run axe against whatever is on screen right now.
 *
 * Returns a bounded summary: the stored report is read back by tooling and shown
 * in logs, so node lists and HTML snippets are capped rather than dumped whole.
 */
/** Contrast of text inside form controls, which axe cannot judge.
 *
 * axe reports inputs, textareas and selects as "incomplete" — it cannot resolve
 * their background when the layout overlaps — so a field rendering its value in
 * near-invisible colours produces no violation at all. That is not hypothetical:
 * a builder field once shipped at 1.2:1 because an undefined custom property fell
 * back to white while the text colour stayed light. This computes the ratio from
 * resolved styles instead, walking ancestors for an opaque backdrop.
 */
const FORM_CONTRAST_PROBE = `(() => {
  const parse = value => {
    const parts = (value || '').match(/[\\d.]+/g);
    if (!parts || parts.length < 3) return null;
    const alpha = parts.length > 3 ? Number(parts[3]) : 1;
    return {r: +parts[0], g: +parts[1], b: +parts[2], a: alpha};
  };
  const luminance = ({r, g, b}) => {
    const channel = value => {
      const v = value / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const blend = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a), a: 1});
  const backdrop = element => {
    let layer = {r: 255, g: 255, b: 255, a: 1};
    const stack = [];
    for (let node = element; node; node = node.parentElement) {
      const colour = parse(getComputedStyle(node).backgroundColor);
      if (colour && colour.a > 0) stack.push(colour);
      if (colour && colour.a === 1) break;
    }
    while (stack.length) layer = blend(stack.pop(), layer);
    return layer;
  };
  const describe = element => {
    const id = element.id ? '#' + element.id : '';
    const classes = (element.getAttribute('class') || '').trim().split(/\\s+/).filter(Boolean).slice(0, 2);
    return element.tagName.toLowerCase() + id + (classes.length ? '.' + classes.join('.') : '');
  };
  const findings = [];
  for (const element of document.querySelectorAll('input, textarea, select')) {
    const style = getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
    if (element.type === 'hidden' || element.type === 'checkbox' || element.type === 'radio') continue;
    const box = element.getBoundingClientRect();
    if (box.width < 2 || box.height < 2) continue;
    // Only judge a control that is actually showing text of its own.
    const shown = element.value || element.textContent || '';
    const placeholder = !shown && element.placeholder ? element.placeholder : '';
    if (!shown && !placeholder) continue;
    const foreground = parse(style.color);
    if (!foreground) continue;
    const text = blend(foreground, backdrop(element));
    const behind = backdrop(element);
    const light = Math.max(luminance(text), luminance(behind));
    const dark = Math.min(luminance(text), luminance(behind));
    const ratio = (light + 0.05) / (dark + 0.05);
    const size = parseFloat(style.fontSize) || 16;
    const bold = Number(style.fontWeight) >= 700;
    const large = size >= 24 || (bold && size >= 18.66);
    const required = large ? 3 : 4.5;
    if (ratio + 0.005 < required) {
      findings.push({target: describe(element), ratio: Math.round(ratio * 100) / 100,
        required, colour: style.color, background: style.backgroundColor,
        kind: shown ? 'value' : 'placeholder'});
    }
  }
  return findings.slice(0, 20);
})()`;

async function auditAccessibility(client, name) {
  const options = JSON.stringify({runOnly: {type: 'tag', values: AXE_TAGS}, resultTypes: ['violations']});
  const violations = await evaluate(client, `(async () => {
    if (!window.axe) return {error: 'axe-core was not injected into this document.'};
    const result = await window.axe.run(document, ${options});
    return {violations: result.violations.map(violation => ({
      id: violation.id,
      impact: violation.impact,
      help: violation.help,
      helpUrl: violation.helpUrl,
      count: violation.nodes.length,
      nodes: violation.nodes.slice(0, 4).map(node => ({
        target: node.target.join(' '),
        summary: (node.failureSummary || '').split('\\n').slice(0, 4).join(' ').slice(0, 300),
        html: node.html.slice(0, 200),
      })),
    }))};
  })()`);
  if (violations.error) throw new Error(violations.error);
  const found = violations.violations;
  const formContrast = await evaluate(client, FORM_CONTRAST_PROBE);
  if (formContrast.length) {
    // Presented as an ordinary serious violation so it is baselined and gated
    // through exactly the same path as everything axe reports.
    found.push({
      id: 'form-control-contrast', impact: 'serious',
      help: 'Text shown inside a form control must meet WCAG AA contrast',
      helpUrl: 'https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html',
      count: formContrast.length,
      nodes: formContrast.slice(0, 4).map(item => ({
        target: item.target,
        summary: `${item.kind} text has contrast ${item.ratio}, needs ${item.required} ` +
                 `(colour ${item.colour} on ${item.background})`,
        html: '',
      })),
    });
  }
  const failing = found.filter(violation => FAILING_IMPACTS.has(violation.impact));
  accessibilityFindings.push({state: name, violations: found});
  if (failing.length) {
    const summary = failing.map(v => `${v.impact} ${v.id} ×${v.count}`).join(', ');
    process.stdout.write(`  ✗ accessibility: ${summary}\n`);
  }
  return failing.length;
}

async function shot(client, name) {
  await new Promise(resolveDelay => setTimeout(resolveDelay, 180));
  const result = await client.send('Page.captureScreenshot', {format: 'png', fromSurface: true, captureBeyondViewport: false});
  await writeFile(join(output, name), Buffer.from(result.data, 'base64'));
  process.stdout.write(`captured ${name}\n`);
  if (scanAccessibility) await auditAccessibility(client, name.replace(/\.png$/, ''));
}

if (accountsMode) {
  // vite.config.js carries esbuild jsx:'automatic'. Without it the build falls back
  // to the classic runtime and every page dies on "React is not defined".
  for (const item of ['src','public','index.html','package.json','package-lock.json','vite.config.js']) {
    await cp(join(root,'template/frontend',item),join(accountsBuild,item),{recursive:true});
  }
  await cp(join(root,'kits/accounts/frontend/src'),join(accountsBuild,'src'),{recursive:true});
  await symlink(join(root,'frontend/node_modules'),join(accountsBuild,'node_modules'),'dir');
}
const build = spawnSync('npm', ['--prefix', accountsBuild || 'frontend', 'run', 'build'], {cwd: root, stdio: 'inherit'});
if (build.status !== 0) process.exit(build.status || 1);
await rm(output, {recursive: true, force: true});
await mkdir(output, {recursive: true});
const profile = await mkdtemp(join(tmpdir(), 'local-foundry-capture-'));
let chrome;
let client;

try {
  await new Promise((resolveListen, rejectListen) => {
    server.once('error', rejectListen);
    server.listen(0, '127.0.0.1', resolveListen);
  });
  const port = server.address().port;
  chrome = spawn(chromePath(), ['--headless=new', '--disable-gpu', '--hide-scrollbars',
    '--remote-debugging-port=0', '--remote-allow-origins=*', `--user-data-dir=${profile}`,
    '--window-size=1440,950', '--no-first-run', `http://127.0.0.1:${port}/#token=visual-fixture`],
  {stdio: ['ignore', 'ignore', 'pipe']});
  let stderr = '';
  const browserWebSocket = await new Promise((resolveSocket, rejectSocket) => {
    const timer = setTimeout(() => rejectSocket(new Error('Chrome did not expose DevTools within 15 seconds.')), 15000);
    chrome.stderr.on('data', chunk => {
      stderr += chunk.toString();
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {clearTimeout(timer); resolveSocket(match[1]);}
    });
    chrome.once('exit', code => {clearTimeout(timer); rejectSocket(new Error(`Chrome exited early (${code}). ${stderr.slice(-500)}`));});
  });
  const debugPort = new URL(browserWebSocket).port;
  let target;
  for (let attempt = 0; attempt < 50 && !target; attempt += 1) {
    const targets = await fetch(`http://127.0.0.1:${debugPort}/json/list`).then(response => response.json());
    target = targets.find(item => item.type === 'page' && item.url.includes(`127.0.0.1:${port}`));
    if (!target) await new Promise(resolveDelay => setTimeout(resolveDelay, 100));
  }
  if (!target) throw new Error('Chrome page target was not created.');
  client = await cdp(target.webSocketDebuggerUrl);
  await client.send('Page.enable');
  await client.send('Runtime.enable');
  // Record page errors before the app loads, so a capture that never reaches its
  // ready state can say why instead of only saying that it did not.
  const errorRecorder = `window.__captureErrors = [];
    addEventListener('error', event => window.__captureErrors.push(
      String(event.message) + (event.filename ? ' @ ' + event.filename + ':' + event.lineno : '')));
    addEventListener('unhandledrejection', event => window.__captureErrors.push('unhandled rejection: ' + String(event.reason)));`;
  await client.send('Page.addScriptToEvaluateOnNewDocument', {source: errorRecorder});
  await evaluate(client, errorRecorder + '\n;true');
  if (scanAccessibility) {
    // Injected from the local package, never fetched at runtime, so the capture
    // still works with no network. addScriptToEvaluateOnNewDocument reinstalls it
    // after every navigation and reload the capture performs.
    const axeSource = await readFile(join(root, 'frontend/node_modules/axe-core/axe.min.js'), 'utf8')
      .catch(() => { throw new Error('axe-core is missing. Run npm --prefix frontend ci, or pass --no-a11y.'); });
    await client.send('Page.addScriptToEvaluateOnNewDocument', {source: axeSource});
    await evaluate(client, axeSource + '\n;Boolean(window.axe)');
  }
  if (accountsMode) {
    const fixedClock = "Date.now = () => Date.parse('2026-09-18T10:30:00Z')";
    await client.send('Page.addScriptToEvaluateOnNewDocument',{source:fixedClock});
    await evaluate(client,fixedClock);
    await waitFor(client, `document.querySelector('.auth-card form') && !document.querySelector('.auth-card button.primary').disabled`);
    await shot(client, '01-sign-in.png');
    await clickText(client, 'Create an account');
    await waitFor(client, `document.querySelector('h2').textContent.includes('home')`);
    await shot(client, '02-registration.png');
    await clickText(client, 'Back to sign in');
    await clickText(client, 'Forgot your password');
    await waitFor(client, `document.querySelector('h2').textContent.includes('fresh')`);
    await shot(client, '03-request-reset.png');
    await client.send('Page.navigate',{url:`http://127.0.0.1:${port}/?capture=reset#action=reset&token=fixture-token-for-ui-only`});
    await waitFor(client, `document.querySelector('h2').textContent.includes('Set your password')`);
    await shot(client, '04-new-password.png');
    await client.send('Page.navigate',{url:`http://127.0.0.1:${port}/?capture=verify#action=verify&token=fixture-token-for-ui-only`});
    await waitFor(client, `document.querySelector('h2').textContent.includes('Verify')`);
    await shot(client, '05-verify-email.png');
    accountsState.signedIn = true;
    await client.send('Page.navigate',{url:`http://127.0.0.1:${port}/?capture=workspace`});
    await waitFor(client, `document.querySelectorAll('.notes article').length === 2`);
    await shot(client, '06-private-workspace.png');
    await clickText(client, 'Billing', 'nav button');
    await waitFor(client, `document.querySelectorAll('.products article').length === 2`);
    await shot(client, '07-billing.png');
    accountsState.mode = 'off';
    await clickText(client, 'Refresh');
    await waitFor(client, `document.querySelector('.section-title .tag')?.textContent === 'PAYMENTS OFF'`);
    await shot(client, '08-payments-disabled.png');
    await clickText(client, 'People & access', 'nav button');
    await waitFor(client, `document.querySelectorAll('tbody tr').length === 3`);
    await shot(client, '09-people-roles.png');
    await clickText(client, 'Operations', 'nav button');
    await waitFor(client, `document.querySelector('.stats')`);
    await shot(client, '10-operations.png');
    await evaluate(client, `window.scrollTo(0,document.body.scrollHeight)`);
    await shot(client, '11-audit-alerts.png');
    await evaluate(client, `window.scrollTo(0,0)`);
    accountsState.role = 'viewer';
    await client.send('Page.reload',{ignoreCache:true});
    await waitFor(client, `document.querySelector('.message')?.textContent.includes('viewer')`);
    await shot(client, '12-viewer-role.png');
    accountsState.role = 'admin'; accountsState.empty = true;
    await client.send('Page.reload',{ignoreCache:true});
    await waitFor(client, `document.querySelector('.empty')`);
    await shot(client, '13-empty-workspace.png');
    accountsState.empty = false;
    await client.send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await client.send('Page.reload',{ignoreCache:true});
    await waitFor(client, `document.querySelector('.notes article')`);
    await shot(client, '14-mobile-workspace.png');
    await clickText(client, 'People & access', 'nav button');
    await waitFor(client, `document.querySelectorAll('tbody tr').length === 3`);
    await shot(client, '15-mobile-people.png');
    accountsState.signedIn = false;
    await client.send('Page.reload',{ignoreCache:true});
    await waitFor(client, `document.querySelector('.auth-card')`);
    await shot(client, '16-mobile-sign-in.png');
  } else {
  await waitFor(client, `document.querySelector('.welcome')`);

  await shot(client, '01-welcome.png');
  await clickText(client, 'Create your first project');
  await waitFor(client, `document.querySelector('.modal')`);
  await shot(client, '02-new-project.png');

  state.project = true;
  await client.send('Page.reload', {ignoreCache: true});
  await waitFor(client, `document.querySelector('.workbench')`);
  await shot(client, '03-project-preview.png');
  await clickText(client, 'Context', '[role="tab"]');
  await waitFor(client, `document.querySelector('.continuity textarea')`);
  await shot(client, '26-project-context.png');
  await clickText(client, 'Roadmap', '[role="tab"]');
  await waitFor(client, `document.querySelector('.continuity ol')`);
  await shot(client, '27-feature-roadmap.png');
  await clickText(client, 'Mobile', '[role="tab"]');
  await waitFor(client, `document.querySelector('.mobile-target')`);
  await shot(client, '28-mobile-build-details.png');
  await evaluate(client, `document.querySelector('.mobile-targets').scrollIntoView({block:'start'})`);
  await shot(client, '29-mobile-build-downloads.png');
  await clickText(client, 'Preview', '[role="tab"]');

  await evaluate(client, `document.querySelector('[aria-label="Set build budget"]').click()`);
  await waitFor(client, `document.querySelector('.limit-grid')`);
  await shot(client, '04-build-limits.png');
  await evaluate(client, `document.querySelector('[aria-label="Close dialog"]').click()`);

  await clickText(client, 'Code', '[role="tab"]');
  await waitFor(client, `document.querySelector('.file-list button')`);
  await clickText(client, 'frontend/src/App.jsx');
  await waitFor(client, `document.querySelector('.source-pane pre').textContent.includes('My reading room')`);
  await shot(client, '05-code.png');

  await clickText(client, 'Logs', '[role="tab"]');
  await waitFor(client, `document.querySelector('.logs-pane pre').textContent.includes('Application startup')`);
  await shot(client, '06-logs.png');

  await clickText(client, 'Versions', '[role="tab"]');
  await waitFor(client, `document.querySelector('.version')`);
  await shot(client, '07-versions.png');
  await evaluate(client, `document.querySelector('.version button').click()`);
  await waitFor(client, `document.querySelector('.modal')`);
  await shot(client, '08-source-restore.png');
  await evaluate(client, `document.querySelector('[aria-label="Close dialog"]').click()`);

  await clickText(client, 'Data', '[role="tab"]');
  await waitFor(client, `document.querySelector('.data-pane')`);
  await shot(client, '09-data-safety.png');
  await evaluate(client, `document.querySelector('.backup button').click()`);
  await waitFor(client, `document.querySelector('.modal')`);
  await shot(client, '10-database-restore.png');
  await evaluate(client, `document.querySelector('[aria-label="Close dialog"]').click()`);

  await clickText(client, 'Save to GitHub');
  await waitFor(client, `document.querySelector('.modal')`);
  await shot(client, '11-github-review.png');
  await clickText(client, 'Review changes');
  await waitFor(client, `document.querySelector('.github-review')`);
  await shot(client, '12-github-diff.png');
  await evaluate(client, `document.querySelector('[aria-label="Close dialog"]').click()`);

  state.active = true;
  await client.send('Page.reload', {ignoreCache: true});
  await waitFor(client, `document.querySelector('.activity-toggle')`);
  await evaluate(client, `document.querySelector('.activity-toggle').click()`);
  await waitFor(client, `document.querySelector('.event-list')`);
  await shot(client, '13-build-activity.png');

  state.active = false;
  state.offline = true;
  await client.send('Page.reload', {ignoreCache: true});
  await waitFor(client, `document.querySelector('.offline-label') && document.querySelector('[aria-label="AI provider"]').value === 'local'`);
  await shot(client, '14-offline-local-ai.png');

  await clickText(client, 'Docs', '[role="tab"]');
  await waitFor(client, `document.querySelector('.document-search')`);
  await evaluate(client, `(() => { const input = document.querySelector('[aria-label="Search local documents"]'); const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; setter.call(input, 'offline security'); input.dispatchEvent(new Event('input', {bubbles: true})); })()`);
  await new Promise(resolveDelay => setTimeout(resolveDelay, 100));
  await evaluate(client, `document.querySelector('.document-search').requestSubmit()`);
  await waitFor(client, `document.querySelectorAll('.document-results article').length === 2`);
  await shot(client, '15-document-search.png');

  await clickText(client, 'Files', '[role="tab"]');
  await waitFor(client, `document.querySelector('.file-plan')`);
  await shot(client, '16-file-automation.png');

  await clickText(client, 'Recovery', '[role="tab"]');
  await waitFor(client, `document.querySelector('.recovery-note')`);
  await shot(client, '17-recovery.png');
  await clickText(client, 'Create export');
  await waitFor(client, `document.querySelector('.modal')`);
  await shot(client, '18-recovery-export.png');
  await evaluate(client, `document.querySelector('[aria-label="Close dialog"]').click()`);
  await clickText(client, 'Import archive');
  await waitFor(client, `document.querySelector('.modal input[type="file"]')`);
  await shot(client, '19-recovery-import.png');
  await evaluate(client, `document.querySelector('[aria-label="Close dialog"]').click()`);

  await evaluate(client, `document.querySelector('[aria-label="System diagnostics"]').click()`);
  await waitFor(client, `document.querySelector('.diagnostic-list')`);
  await shot(client, '20-diagnostics.png');
  await evaluate(client, `document.querySelector('[aria-label="Close dialog"]').click()`);

  await client.send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await client.send('Page.reload', {ignoreCache: true});
  await waitFor(client, `document.querySelector('.workbench')`);
  await shot(client, '21-mobile-preview.png');
  await client.send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 950, deviceScaleFactor: 1, mobile: false});
  await clickText(client, 'Build controls');
  await waitFor(client, `document.querySelector('.build-options')`);
  await shot(client, '22-build-controls.png');
  await evaluate(client, `document.querySelector('[aria-label="Close dialog"]').click()`);
  await clickText(client, 'Packages', '[role="tab"]');
  await waitFor(client, `document.querySelector('.upgrade-pane .file-plan')`);
  await shot(client, '23-package-approval.png');
  await clickText(client, 'Visual', '[role="tab"]');
  await waitFor(client, `document.querySelector('.visual-form')`);
  await evaluate(client, `document.querySelector('.visual-form details').open = true`);
  await shot(client, '24-browser-checks.png');
  await clickText(client, 'Release', '[role="tab"]');
  await waitFor(client, `document.querySelector('.release-steps')`);
  await shot(client, '25-release-review.png');
  }
  process.stdout.write(`\nUI capture complete: ${output}\n`);
  if (scanAccessibility) {
    // A finding is identified by state + rule + element, not by count, so moving
    // an existing problem around is still caught while a re-render is not.
    const fingerprints = new Map();
    const byImpact = {critical: 0, serious: 0, moderate: 0, minor: 0};
    for (const finding of accessibilityFindings) {
      for (const violation of finding.violations) {
        if (violation.impact in byImpact) byImpact[violation.impact] += violation.count;
        if (!FAILING_IMPACTS.has(violation.impact)) continue;
        for (const node of violation.nodes) {
          fingerprints.set(`${finding.state} | ${violation.id} | ${node.target}`,
            {state: finding.state, rule: violation.id, impact: violation.impact,
             target: node.target, summary: node.summary});
        }
      }
    }
    const current = [...fingerprints.keys()].sort();
    const report = {
      generated_at: new Date().toISOString(),
      mode: accountsMode ? 'accounts' : 'builder',
      tags: AXE_TAGS,
      failing_impacts: [...FAILING_IMPACTS],
      states_scanned: accessibilityFindings.length,
      totals: byImpact,
      findings: accessibilityFindings.filter(finding => finding.violations.length),
    };
    await writeFile(join(output, 'accessibility.json'), JSON.stringify(report, null, 2));
    process.stdout.write(
      `Accessibility: ${report.states_scanned} states scanned · ` +
      `${byImpact.critical} critical, ${byImpact.serious} serious, ` +
      `${byImpact.moderate} moderate, ${byImpact.minor} minor\n`);

    if (updateBaseline) {
      await writeFile(baselinePath, JSON.stringify({
        note: 'Known accessibility findings. New findings outside this list fail the capture. ' +
              'Shrink this file deliberately; regenerate with node scripts/capture-ui.mjs --a11y-baseline.',
        updated_at: new Date().toISOString(), accepted: current,
        detail: current.map(key => fingerprints.get(key)),
      }, null, 2));
      process.stdout.write(`Baseline rewritten with ${current.length} accepted findings: ${baselinePath}\n`);
    } else {
      const baseline = await readFile(baselinePath, 'utf8').then(JSON.parse).catch(() => null);
      if (!baseline) {
        process.stdout.write(
          `No accessibility baseline yet. Create one with --a11y-baseline, ` +
          `then new findings will fail this capture. Current: ${current.length}\n`);
      } else {
        const accepted = new Set(baseline.accepted);
        const regressions = current.filter(key => !accepted.has(key));
        const fixed = baseline.accepted.filter(key => !fingerprints.has(key));
        if (fixed.length) process.stdout.write(`${fixed.length} baselined finding(s) no longer occur. Rerun with --a11y-baseline to lock that in.\n`);
        if (regressions.length) {
          process.stdout.write(`\nNew accessibility findings (${regressions.length}):\n`);
          for (const key of regressions.slice(0, 25)) {
            const finding = fingerprints.get(key);
            process.stdout.write(`  ${finding.impact} · ${finding.rule} · ${finding.state} · ${finding.target}\n    ${finding.summary.slice(0, 160)}\n`);
          }
          if (regressions.length > 25) process.stdout.write(`  …and ${regressions.length - 25} more in accessibility.json\n`);
          process.exitCode = 1;
        } else {
          process.stdout.write(`No new accessibility findings against the baseline (${accepted.size} accepted).\n`);
        }
      }
    }
  }
} finally {
  if (client) client.close();
  if (chrome && !chrome.killed) {
    // Chrome keeps writing to its profile until it exits, so removing the
    // directory immediately raced and failed with ENOTEMPTY.
    const exited = new Promise(resolveExit => chrome.once('exit', resolveExit));
    chrome.kill('SIGTERM');
    const forced = setTimeout(() => chrome.kill('SIGKILL'), 5000);
    await Promise.race([exited, new Promise(resolveTimeout => setTimeout(resolveTimeout, 8000))]);
    clearTimeout(forced);
  }
  await new Promise(resolveClose => server.close(resolveClose));
  await rm(profile, {recursive: true, force: true, maxRetries: 5, retryDelay: 200});
  if (accountsBuild) await rm(accountsBuild, {recursive:true,force:true});
}
