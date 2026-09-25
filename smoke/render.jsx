import './shim.js';
import { renderToString } from 'react-dom/server';
import App from '../src/App.jsx';
import DocumentsPanel from '../src/panels/DocumentsPanel.jsx';
import FilesPanel from '../src/panels/FilesPanel.jsx';
import RecoveryPanel from '../src/panels/RecoveryPanel.jsx';
import { MobileView } from '../src/panels/MobilePanel.jsx';

const project = {
  id: 'p1', name: 'Demo',
  documents: { indexed_files: 12, chunks: 340, folder: '/Users/demo/.data/workspace/documents', ocr_available: true },
  file_plans: [{ id: 'fp1', prompt: 'Organize invoices', status: 'planned', created_at: '2026-09-18T10:00:00Z',
    operations: [{ op: 'move', source: 'a.pdf', destination: 'invoices/a.pdf' }] }],
  recovery_exports: [{ id: 'r1', filename: 'demo.lfr', bytes: 5_242_880, created_at: '2026-09-18T10:00:00Z' }],
};
const noop = () => {};
const mobileProps = { project, config: { offline_only: false }, running: false, builds: [],
  values: { origin: 'https://app.example.com', name: 'Demo', app_id: 'com.example.demo', version: '1.0.0', build_number: '1', team_id: 'ABCDEFGHIJ', export_method: 'debugging', allow_network: true, icon_source: '/Users/demo/brand/logo.png', icon_background: '#101510', keystore_path: '/Users/demo/keys/upload.jks', key_alias: 'upload', store_password: 'secret123', key_password: '' },
  capabilities: { apk: { available: true, blockers: [] }, ipa: { available: false, blockers: ['Requires macOS with Xcode.'] } },
  setValues: noop, start: noop, refresh: noop, cancel: noop, download: noop, showLog: noop, log: null };
const cases = {
  App: <App />,
  MobileWindows: <MobileView {...mobileProps} />,
  MobileReady: <MobileView {...mobileProps} builds={[{ id: 'a'.repeat(32), target: 'apk', status: 'completed', phase: 'Ready to download', version: '1.0.0', build_number: 1, created_at: '2026-09-22T12:00:00Z', origin: 'https://app.example.com', bytes: 5120000, filename: 'demo.apk', sha256: 'b'.repeat(64) }]} />,
  MobileOffline: <MobileView {...mobileProps} config={{ offline_only: true }} />,
  DocumentsPanel: <DocumentsPanel project={project} id="p1" running={false} busy={false} perform={noop}
    launch={noop} searchDocuments={noop} documentQuery="invoice" setDocumentQuery={noop}
    documentResults={[{ citation: 'notes.md:3', snippet: 'A snippet.' }]} />,
  DocumentsPanelEmpty: <DocumentsPanel project={project} id="p1" running={true} busy={true} perform={noop}
    launch={noop} searchDocuments={noop} documentQuery="" setDocumentQuery={noop} documentResults={[]} />,
  FilesPanel: <FilesPanel project={project} id="p1" config={{ files_folder: '/Users/demo/files' }}
    running={false} perform={noop} launch={noop} setMode={noop} setPrompt={noop} />,
  FilesPanelEmpty: <FilesPanel project={{ ...project, file_plans: [] }} id="p1"
    config={{ files_folder: '/Users/demo/files' }} running={true} perform={noop} launch={noop} setMode={noop} setPrompt={noop} />,
  RecoveryPanel: <RecoveryPanel project={project} running={false} perform={noop} setModal={noop}
    setRecoveryPassword={noop} setRecoveryConfirm={noop} openRecoveryImport={noop} />,
  RecoveryPanelEmpty: <RecoveryPanel project={{ ...project, recovery_exports: [] }} running={true} perform={noop}
    setModal={noop} setRecoveryPassword={noop} setRecoveryConfirm={noop} openRecoveryImport={noop} />,
};
let failed = 0;
for (const [name, element] of Object.entries(cases)) {
  try {
    const html = renderToString(element);
    if (!html.length) throw new Error('rendered nothing');
    console.log(`ok    ${name.padEnd(20)} ${html.length} chars`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL  ${name.padEnd(20)} ${error.message}`);
  }
}
console.log(failed ? `${failed} case(s) failed` : 'all render cases passed');
process.exit(failed ? 1 : 0);
