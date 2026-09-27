/**
 * LocalFoundry Comprehensive End-to-End (E2E) Test Suite
 * Tests full lifecycle: Server APIs, Diagnostics, Local Codebase RAG, SQLite Vector Store,
 * Prompt Optimizer, Build Execution, Mobile Engine, Documents Search, and Packaging.
 */

const BASE_URL = process.env.TEST_BASE_URL || 'http://localhost:3000';

interface TestResult {
  suite: string;
  name: string;
  passed: boolean;
  durationMs: number;
  details?: string;
  error?: string;
}

const results: TestResult[] = [];

async function runStep(suite: string, name: string, fn: () => Promise<void>) {
  const start = Date.now();
  try {
    await fn();
    const durationMs = Date.now() - start;
    results.push({ suite, name, passed: true, durationMs });
    console.log(`  ✓ [PASS] ${name} (${durationMs}ms)`);
  } catch (err: any) {
    const durationMs = Date.now() - start;
    results.push({ suite, name, passed: false, durationMs, error: err?.message || String(err) });
    console.error(`  ✗ [FAIL] ${name} (${durationMs}ms): ${err?.message || err}`);
  }
}

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

async function runAllE2ETests() {
  console.log('\n===============================================================');
  console.log('       LOCALFOUNDRY END-TO-END (E2E) VERIFICATION SUITE         ');
  console.log(`       Target Endpoint: ${BASE_URL}                            `);
  console.log('===============================================================\n');

  let testProjectId = '';
  let initialProjectsCount = 0;
  let testRunId = '';

  // -------------------------------------------------------------------------
  // SUITE 1: System Health, Configuration & Metadata
  // -------------------------------------------------------------------------
  console.log('Suite 1: System Health & Configuration');

  await runStep('System Health', 'GET /api/config returns active providers and RAG config', async () => {
    const res = await fetch(`${BASE_URL}/api/config`);
    assert(res.ok, `Status ${res.status}`);
    const data = await res.json();
    assert(!!data.providers, 'Expected providers map');
    assert(!!data.providers.local, 'Expected local provider');
    assert(!!data.providers.hybrid, 'Expected hybrid provider');
    assert(data.codebase_rag?.enabled === true, 'Expected codebase_rag enabled');
    assert(data.codebase_rag?.embedding_model === 'nomic-embed-text', 'Expected nomic-embed-text model');
    assert(data.codebase_rag?.vector_dimension === 768, 'Expected 768 vector dimension');
  });

  await runStep('System Health', 'GET /api/diagnostics verifies system checks and vector index readiness', async () => {
    const res = await fetch(`${BASE_URL}/api/diagnostics`);
    assert(res.ok, `Status ${res.status}`);
    const data = await res.json();
    assert(data.checks?.vector_index?.status === 'passed', 'Vector index service status passed');
    assert(data.checks?.builder_database?.status === 'passed', 'Builder database status passed');
  });

  await runStep('System Health', 'GET /api/system/status healthcheck endpoint responds healthy', async () => {
    const res = await fetch(`${BASE_URL}/api/system/status`);
    assert(res.ok, `Status ${res.status}`);
    const data = await res.json();
    assert(data.status === 'healthy', 'Expected status healthy');
    assert(data.services?.vector_index?.status === 'passed', 'Vector index ready');
  });

  // -------------------------------------------------------------------------
  // SUITE 2: Project Management & Multi-File Ingestion
  // -------------------------------------------------------------------------
  console.log('\nSuite 2: Project Management & Lifecycle');

  await runStep('Project Management', 'GET /api/projects lists active projects', async () => {
    const res = await fetch(`${BASE_URL}/api/projects`);
    assert(res.ok, `Status ${res.status}`);
    const list = await res.json();
    assert(Array.isArray(list), 'Projects must be an array');
    initialProjectsCount = list.length;
    assert(initialProjectsCount > 0, 'At least one default project should exist');
  });

  await runStep('Project Management', 'POST /api/projects provisions a new project with source files', async () => {
    const payload = {
      name: 'E2E Test Vault App',
      files: {
        'frontend/src/App.jsx': `
import React, { useState } from 'react';
export default function App() {
  const [secrets, setSecrets] = useState(['API_KEY', 'DB_PASS']);
  return (
    <div className="vault-container">
      <h1>Secure Vault</h1>
      <p>Total items: {secrets.length}</p>
    </div>
  );
}
`,
        'frontend/src/vault.css': `
.vault-container {
  background: #0f172a;
  color: #38bdf8;
  padding: 32px;
  border-radius: 12px;
}
`,
        'backend/vault_api.py': `
from fastapi import FastAPI
app = FastAPI()

@app.get("/api/vault/health")
def health():
    return {"status": "secure", "locked": False}
`,
        'database/schema.sql': `
CREATE TABLE IF NOT EXISTS vault_secrets (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  encrypted_val TEXT NOT NULL
);
`
      }
    };

    const res = await fetch(`${BASE_URL}/api/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    assert(res.status === 201, `Expected 201 Created, got ${res.status}`);
    const created = await res.json();
    assert(!!created.id, 'Expected project ID');
    assert(created.name === 'E2E Test Vault App', 'Expected project name');
    assert(Object.keys(created.files).length === 4, 'Expected 4 files created');
    testProjectId = created.id;
  });

  await runStep('Project Management', 'GET /api/projects/:id returns full project manifest and source digest', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}`);
    assert(res.ok, `Status ${res.status}`);
    const proj = await res.json();
    assert(proj.id === testProjectId, 'Matching ID');
    assert(!!proj.source_digest, 'Expected SHA-256 source digest');
    assert(proj.versions.length >= 1, 'Expected at least initial version checkpoint');
  });

  // -------------------------------------------------------------------------
  // SUITE 3: Local Codebase RAG & SQLite Vector Store
  // -------------------------------------------------------------------------
  console.log('\nSuite 3: Local Codebase RAG & SQLite Vector Store');

  await runStep('Codebase RAG', 'GET /api/projects/:id/rag/status confirms SQLite index & nomic-embed-text', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/rag/status`);
    assert(res.ok, `Status ${res.status}`);
    const rag = await res.json();
    assert(rag.enabled === true, 'RAG enabled');
    assert(rag.embedding_model === 'nomic-embed-text', 'Expected nomic-embed-text');
    assert(rag.vector_dimension === 768, 'Expected 768 dimensions');
    assert(rag.indexed_files_count === 4, `Expected 4 indexed files, got ${rag.indexed_files_count}`);
    assert(rag.indexed_chunks_count >= 4, 'Expected chunk embeddings generated');
    assert(rag.total_codebase_tokens > 0, 'Codebase token count should be > 0');
    assert(rag.sqlite_database.includes(testProjectId), 'SQLite DB path references project');
  });

  await runStep('Codebase RAG', 'POST /api/projects/:id/rag/search evaluates semantic ranking for Frontend UI prompt', async () => {
    const searchBody = {
      query: 'Styling vault container background and React state secrets display',
      top_k: 2,
      threshold: 0.35,
    };
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/rag/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(searchBody),
    });
    assert(res.ok, `Status ${res.status}`);
    const result = await res.json();
    assert(result.matched_files.length > 0, 'Should match files for frontend query');
    const matchedPaths = result.matched_files.map((f: any) => f.file_path);
    assert(
      matchedPaths.includes('frontend/src/App.jsx') || matchedPaths.includes('frontend/src/vault.css'),
      `Expected frontend files matched, got: ${matchedPaths.join(', ')}`
    );
    assert(result.tokens_saved > 0, 'Should save prompt tokens by pruning');
    assert(result.token_reduction_pct > 0, 'Token reduction % should be positive');
  });

  await runStep('Codebase RAG', 'POST /api/projects/:id/rag/search evaluates semantic ranking for Backend FastAPI prompt', async () => {
    const searchBody = {
      query: 'FastAPI health endpoint and SQL database migrations',
      top_k: 2,
      threshold: 0.35,
    };
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/rag/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(searchBody),
    });
    assert(res.ok, `Status ${res.status}`);
    const result = await res.json();
    const matchedPaths = result.matched_files.map((f: any) => f.file_path);
    assert(
      matchedPaths.includes('backend/vault_api.py') || matchedPaths.includes('database/schema.sql'),
      `Expected backend/sql files matched, got: ${matchedPaths.join(', ')}`
    );
  });

  await runStep('Codebase RAG', 'POST /api/projects/:id/rag/config modifies threshold & top_k', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/rag/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ top_k: 4, similarity_threshold: 0.50 }),
    });
    assert(res.ok, `Status ${res.status}`);
    const conf = await res.json();
    assert(conf.top_k === 4, 'top_k updated');
    assert(conf.similarity_threshold === 0.50, 'threshold updated');
  });

  await runStep('Codebase RAG', 'POST /api/projects/:id/rag/reindex triggers clean SQLite index synchronization', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/rag/reindex`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    assert(res.ok, `Status ${res.status}`);
    const status = await res.json();
    assert(status.indexed_files_count === 4, 'All 4 files re-indexed');
  });

  await runStep('Codebase RAG', 'GET /api/projects/:id/rag/queries retrieves query audit log', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/rag/queries`);
    assert(res.ok, `Status ${res.status}`);
    const queries = await res.json();
    assert(Array.isArray(queries), 'Expected array of query logs');
    assert(queries.length >= 2, 'Should contain our executed queries');
  });

  await runStep('Codebase RAG', 'GET /api/projects/:id/rag/export-db downloads SQLite binary database file', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/rag/export-db`);
    assert(res.ok, `Status ${res.status}`);
    const contentType = res.headers.get('content-type');
    assert(contentType === 'application/x-sqlite3', `Expected application/x-sqlite3, got ${contentType}`);
    const buffer = await res.arrayBuffer();
    assert(buffer.byteLength > 100, `Buffer size too small: ${buffer.byteLength} bytes`);
  });

  // -------------------------------------------------------------------------
  // SUITE 4: AI Build Execution & Prompt Token Pruning
  // -------------------------------------------------------------------------
  console.log('\nSuite 4: AI Build Execution & RAG Event Stream');

  await runStep('AI Build', 'POST /api/projects/:id/build triggers build with RAG token optimizer', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: 'Add vault master unlock button and status indicator in App.jsx',
      }),
    });
    assert(res.ok, `Status ${res.status}`);
    const data = await res.json();
    assert(!!data.run_id, 'Expected run_id');
    testRunId = data.run_id;
  });

  await runStep('AI Build', 'GET /api/runs/:runId verifies RAG events, token cut & preview URL', async () => {
    const res = await fetch(`${BASE_URL}/api/runs/${testRunId}`);
    assert(res.ok, `Status ${res.status}`);
    const run = await res.json();
    assert(run.status === 'completed', `Expected completed run status, got: ${run.status}`);
    assert(Array.isArray(run.events), 'Expected events array');

    // Check for RAG event logs
    const ragEvent = run.events.find((e: any) => e.text && e.text.includes('[Local Codebase RAG · nomic-embed-text]'));
    assert(!!ragEvent, 'Expected Local Codebase RAG status event');

    const tokenOptEvent = run.events.find((e: any) => e.text && e.text.includes('[Token Optimizer]'));
    assert(!!tokenOptEvent, 'Expected Token Optimizer event');

    // Check for preview URL
    const previewEvent = run.events.find((e: any) => e.kind === 'preview');
    assert(!!previewEvent && !!previewEvent.url, 'Expected preview URL event');

    // Check token usage
    assert(run.usage?.input_tokens > 0, 'Usage input tokens > 0');
  });

  await runStep('AI Build', 'Check project versions & message history updated', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}`);
    const proj = await res.json();
    assert(proj.versions.length >= 2, 'Version history should have incremented');
    const lastMsg = proj.messages[proj.messages.length - 1];
    assert(lastMsg.role === 'assistant', 'Last message should be from assistant');
    assert(lastMsg.content.includes('Codebase RAG Active'), 'Assistant message should cite RAG active optimization');
  });

  // -------------------------------------------------------------------------
  // SUITE 5: Live Preview Frame & Web Rendering
  // -------------------------------------------------------------------------
  console.log('\nSuite 5: Interactive Live Preview Frame');

  await runStep('Preview Frame', 'GET /api/projects/:id/preview-frame serves sandboxed HTML with hot scripts', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/preview-frame`);
    assert(res.ok, `Status ${res.status}`);
    const html = await res.text();
    assert(html.includes('<!DOCTYPE html>') || html.includes('<html>'), 'Expected HTML doctype');
    assert(html.includes('Live Preview Sandbox'), 'Expected Live Preview Sandbox badge');
    assert(html.includes('E2E Test Vault App'), 'Expected project name rendered in preview');
  });

  // -------------------------------------------------------------------------
  // SUITE 6: Document Knowledgebase & Semantic Search
  // -------------------------------------------------------------------------
  console.log('\nSuite 6: Documents & Knowledgebase Search');

  await runStep('Documents', 'POST /api/projects/:id/documents/search searches project documents', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/documents/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'architecture decisions and data model' }),
    });
    assert(res.ok, `Status ${res.status}`);
    const data = await res.json();
    assert(Array.isArray(data.results), 'Expected results array');
    assert(data.results.length > 0, 'Expected document citations returned');
  });

  await runStep('Documents', 'GET /api/projects/:id/documents/search query parameter search', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/documents/search?q=architecture`);
    assert(res.ok, `Status ${res.status}`);
    const data = await res.json();
    assert(Array.isArray(data.results), 'Expected results array');
  });

  // -------------------------------------------------------------------------
  // SUITE 7: Mobile Artifacts & Build Pipeline
  // -------------------------------------------------------------------------
  console.log('\nSuite 7: Mobile Build Engine');

  await runStep('Mobile Engine', 'GET /api/projects/:id/mobile/builds retrieves mobile release history', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/mobile/builds`);
    assert(res.ok, `Status ${res.status}`);
    const builds = await res.json();
    assert(Array.isArray(builds), 'Expected array of mobile builds');
  });

  await runStep('Mobile Engine', 'POST /api/projects/:id/mobile/builds triggers Android APK compilation simulation', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/mobile/builds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target: 'apk',
        name: 'Vault Mobile',
        app_id: 'com.localfoundry.vault',
        version: '1.0.0',
        build_number: 1,
      }),
    });
    assert(res.status === 202, `Expected 202 Accepted, got ${res.status}`);
    const data = await res.json();
    assert(data.build?.target === 'apk', 'Target APK');
    assert(data.build?.status === 'completed', 'Completed status');
    assert(data.build?.filename.endsWith('.apk'), 'Filename ends with .apk');
  });

  // -------------------------------------------------------------------------
  // SUITE 8: Project Archival & ZIP Export
  // -------------------------------------------------------------------------
  console.log('\nSuite 8: Project Packaging & ZIP Export');

  await runStep('Packaging', 'GET /api/projects/:id/download.zip generates valid ZIP archive', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/download.zip`);
    assert(res.ok, `Status ${res.status}`);
    const contentType = res.headers.get('content-type');
    assert(contentType === 'application/zip', `Expected application/zip, got ${contentType}`);
    const buffer = await res.arrayBuffer();
    assert(buffer.byteLength > 100, `ZIP archive too small (${buffer.byteLength} bytes)`);
    // Verify standard PK ZIP header bytes: 0x50, 0x4B, 0x03, 0x04
    const headerBytes = new Uint8Array(buffer.slice(0, 4));
    assert(
      headerBytes[0] === 0x50 && headerBytes[1] === 0x4B && headerBytes[2] === 0x03 && headerBytes[3] === 0x04,
      'Invalid ZIP magic bytes'
    );
  });

  // -------------------------------------------------------------------------
  // SUITE 9: Project Continuity & Recovery
  // -------------------------------------------------------------------------
  console.log('\nSuite 9: Project Continuity & Snapshot Recovery');

  let recoveryExportId = '';

  await runStep('Continuity', 'POST /api/projects/:id/recovery/export creates encrypted snapshot', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}/recovery/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ passphrase: 'test-secure-passphrase-123' }),
    });
    assert(res.ok, `Status ${res.status}`);
    const data = await res.json();
    assert(!!data.export?.id, 'Expected export ID');
    assert(data.export.filename.endsWith('.enc'), 'Expected .enc file extension');
    recoveryExportId = data.export.id;
  });

  await runStep('Continuity', 'GET project verifies recovery_exports recorded', async () => {
    const res = await fetch(`${BASE_URL}/api/projects/${testProjectId}`);
    const proj = await res.json();
    const exp = proj.recovery_exports.find((e: any) => e.id === recoveryExportId);
    assert(!!exp, 'Expected recovery export recorded in project history');
  });

  // -------------------------------------------------------------------------
  // SUMMARY
  // -------------------------------------------------------------------------
  console.log('\n===============================================================');
  const total = results.length;
  const passed = results.filter(r => r.passed).length;
  const failed = results.filter(r => !r.passed).length;
  const totalDuration = results.reduce((acc, r) => acc + r.durationMs, 0);

  console.log(`TOTAL TESTS: ${total}`);
  console.log(`PASSED:      ${passed}`);
  console.log(`FAILED:      ${failed}`);
  console.log(`TIME:        ${totalDuration}ms`);
  console.log('===============================================================\n');

  if (failed > 0) {
    console.error('Failed test summary:');
    results.filter(r => !r.passed).forEach(r => {
      console.error(`- [${r.suite}] ${r.name}: ${r.error}`);
    });
    process.exit(1);
  } else {
    console.log('ALL LOCALFOUNDRY E2E TESTS COMPLETED CLEANLY WITH 100% SUCCESS!\n');
    process.exit(0);
  }
}

runAllE2ETests().catch(err => {
  console.error('Fatal E2E Error:', err);
  process.exit(1);
});
