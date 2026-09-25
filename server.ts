import express, { Request, Response } from 'express';
import cors from 'cors';
import crypto from 'crypto';
import path from 'path';
import fs from 'fs';
import archiver from 'archiver';
import { createServer as createViteServer } from 'vite';

interface ProjectFile {
  path: string;
  content: string;
  size: number;
  modified: string;
}

interface ProjectVersion {
  id: string;
  project_id: string;
  label: string;
  digest: string;
  created_at: string;
}

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  mode: string;
}

interface RunEvent {
  id: number;
  kind: string;
  text: string;
  url?: string;
  timestamp: string;
}

interface Run {
  id: string;
  project_id: string;
  kind: string;
  status: 'running' | 'completed' | 'cancelled' | 'failed';
  created_at: string;
  events: RunEvent[];
  usage: {
    input_tokens: number;
    output_tokens: number;
    requests: number;
    retries: number;
    estimated_usd: number;
    limits: {
      budget_usd: number;
      max_input_tokens: number;
      max_output_tokens: number;
      input_rate: number;
      output_rate: number;
    };
  };
}

interface ProjectContext {
  body: {
    requirements: string;
    architecture: string;
    data_model: string;
    decisions: string;
    questions: string;
  };
  revision: number;
  agent_notes: string;
  updated_at: string;
}

interface Project {
  id: string;
  name: string;
  profile: 'starter' | 'accounts';
  created_at: string;
  repo: string | null;
  preview_url: string | null;
  sync_state: Record<string, any>;
  last_validation: any;
  source_digest: string;
  messages: Message[];
  versions: ProjectVersion[];
  backups: any[];
  file_plans: any[];
  documents: { status: string; count: number };
  recovery_exports: any[];
  dependency_requests: any[];
  visual_checks: any[];
  context: ProjectContext;
  feature_plans: any[];
  journeys: any[];
  active_run: string | null;
  active_run_kind: string | null;
  files: Record<string, string>; // path -> content
}

const projects = new Map<string, Project>();
const runs = new Map<string, Run>();
let nextMessageId = 1;
let nextEventId = 1;

function generateId(): string {
  return crypto.randomBytes(16).toString('hex');
}

function computeDigest(files: Record<string, string>): string {
  const hash = crypto.createHash('sha256');
  const sortedKeys = Object.keys(files).sort();
  for (const key of sortedKeys) {
    hash.update(key);
    hash.update(files[key]);
  }
  return hash.digest('hex');
}

function createDefaultFiles(name: string, profile: 'starter' | 'accounts'): Record<string, string> {
  const isAccounts = profile === 'accounts';
  return {
    'frontend/src/App.jsx': `import React, { useState } from 'react';
import './style.css';

export default function App() {
  const [items, setItems] = useState([
    { id: 1, title: 'Morning meditation & breathwork', completed: true, streak: 12 },
    { id: 2, title: 'Read 20 pages of non-fiction', completed: false, streak: 5 },
    { id: 3, title: '30-minute outdoor walk', completed: true, streak: 18 },
    { id: 4, title: 'Write daily reflection journal', completed: false, streak: 3 },
  ]);
  const [newTitle, setNewTitle] = useState('');

  const toggle = (id) => {
    setItems(items.map(item => item.id === id ? { ...item, completed: !item.completed, streak: item.completed ? item.streak - 1 : item.streak + 1 } : item));
  };

  const addItem = (e) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setItems([...items, { id: Date.now(), title: newTitle.trim(), completed: false, streak: 1 }]);
    setNewTitle('');
  };

  return (
    <div className="habit-app">
      <header className="habit-header">
        <div>
          <span className="badge">${isAccounts ? 'Accounts Mode' : 'Starter Mode'}</span>
          <h1>${name}</h1>
          <p className="subtitle">Track your daily practices and build compounding momentum.</p>
        </div>
      </header>

      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-val">{items.filter(i => i.completed).length} / {items.length}</span>
          <span className="stat-lbl">Completed Today</span>
        </div>
        <div className="stat-card">
          <span className="stat-val">18 days</span>
          <span className="stat-lbl">Best Streak</span>
        </div>
        <div className="stat-card">
          <span className="stat-val">88%</span>
          <span className="stat-lbl">Weekly Consistency</span>
        </div>
      </div>

      <form onSubmit={addItem} className="habit-form">
        <input
          type="text"
          placeholder="Add a new daily habit..."
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
        />
        <button type="submit">Add Habit</button>
      </form>

      <ul className="habit-list">
        {items.map(item => (
          <li key={item.id} className={item.completed ? 'completed' : ''} onClick={() => toggle(item.id)}>
            <div className="checkbox">{item.completed ? '✓' : ''}</div>
            <span className="title">{item.title}</span>
            <span className="streak">{item.streak} day streak 🔥</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
`,
    'frontend/src/style.css': `
:root {
  --bg: #0e1210;
  --surface: #151b18;
  --border: #222d27;
  --accent: #10b981;
  --accent-soft: rgba(16, 185, 129, 0.15);
  --text: #f0fdf4;
  --muted: #85a392;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
}

.habit-app {
  max-width: 680px;
  margin: 40px auto;
  padding: 24px;
}

.habit-header {
  margin-bottom: 28px;
}

.badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  background: var(--accent-soft);
  color: var(--accent);
  padding: 4px 10px;
  border-radius: 9999px;
  margin-bottom: 8px;
}

.habit-header h1 {
  margin: 4px 0 8px;
  font-size: 28px;
  letter-spacing: -0.02em;
}

.subtitle {
  color: var(--muted);
  margin: 0;
  font-size: 15px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 16px;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
}

.stat-val {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
}

.stat-lbl {
  font-size: 12px;
  color: var(--muted);
  margin-top: 4px;
}

.habit-form {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.habit-form input {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 12px 16px;
  border-radius: 10px;
  color: var(--text);
  font-size: 14px;
  outline: none;
}

.habit-form input:focus {
  border-color: var(--accent);
}

.habit-form button {
  background: var(--accent);
  color: #064e3b;
  border: none;
  font-weight: 600;
  padding: 0 20px;
  border-radius: 10px;
  cursor: pointer;
}

.habit-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.habit-list li {
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 14px 18px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.habit-list li:hover {
  border-color: #2e3d35;
}

.habit-list li.completed {
  opacity: 0.65;
}

.checkbox {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 2px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--accent);
}

.habit-list li.completed .checkbox {
  background: var(--accent-soft);
  border-color: var(--accent);
}

.habit-list li.completed .title {
  text-decoration: line-through;
}

.title {
  flex: 1;
  font-size: 15px;
}

.streak {
  font-size: 13px;
  color: var(--muted);
}
`,
    'backend/app/main.py': `from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI(title="${name} API")

class Habit(BaseModel):
    id: int
    title: str
    completed: bool
    streak: int

@app.get("/api/habits", response_model=List[Habit])
def list_habits():
    return [
        {"id": 1, "title": "Morning meditation", "completed": True, "streak": 12},
        {"id": 2, "title": "Read 20 pages", "completed": False, "streak": 5},
    ]

@app.post("/api/habits", response_model=Habit)
def create_habit(habit: Habit):
    return habit
`,
    'backend/migrations/001_initial.sql': `
CREATE TABLE IF NOT EXISTS habits (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    completed BOOLEAN DEFAULT FALSE,
    streak INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
`,
  };
}

function seedInitialProject(): Project {
  const id = generateId();
  const name = 'Everyday Habit Journal';
  const profile = 'accounts';
  const files = createDefaultFiles(name, profile);
  const digest = computeDigest(files);

  const initialProject: Project = {
    id,
    name,
    profile,
    created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
    repo: null,
    preview_url: `/api/projects/${id}/preview-frame`,
    sync_state: {},
    last_validation: {
      status: 'passed',
      source_digest: digest,
      gate_version: 6,
      checked_at: new Date(Date.now() - 3600000).toISOString(),
    },
    source_digest: digest,
    messages: [
      {
        id: nextMessageId++,
        role: 'user',
        content: 'Build a habit journal with daily check-ins, a weekly overview, and progress cards. Use PostgreSQL for persistence.',
        created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
        mode: 'coder',
      },
      {
        id: nextMessageId++,
        role: 'assistant',
        content: 'Created the habit journal application with responsive cards, streak tracker, and automated state updates. The database migrations and endpoints are configured and validated.',
        created_at: new Date(Date.now() - 3600000 * 1.9).toISOString(),
        mode: 'coder',
      },
    ],
    versions: [
      {
        id: generateId(),
        project_id: id,
        label: 'Starting template',
        digest: digest,
        created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
      },
      {
        id: generateId(),
        project_id: id,
        label: 'Added streak tracking and stats grid',
        digest: digest,
        created_at: new Date(Date.now() - 3600000 * 1.9).toISOString(),
      },
    ],
    backups: [
      {
        id: generateId(),
        name: 'Auto-snapshot before preview migrations',
        created_at: new Date(Date.now() - 3600000 * 1.8).toISOString(),
        size: 14200,
      },
    ],
    file_plans: [],
    documents: { status: 'indexed', count: 3 },
    recovery_exports: [],
    dependency_requests: [],
    visual_checks: [
      {
        id: generateId(),
        viewport: 'desktop',
        status: 'passed',
        created_at: new Date(Date.now() - 3600000 * 1.5).toISOString(),
      },
    ],
    context: {
      body: {
        requirements: 'Daily habit tracking with persistence, streaks, and weekly statistics.',
        architecture: 'React frontend with dark mode palette, FastAPI REST endpoints, and PostgreSQL schema.',
        data_model: 'habits table with id, title, completed, streak, and timestamp fields.',
        decisions: 'Local storage caching with backend sync on change.',
        questions: 'Add category tags or multi-user accounts in next release?',
      },
      revision: 1,
      agent_notes: 'Components are organized cleanly in frontend/src with CSS variables.',
      updated_at: new Date(Date.now() - 3600000).toISOString(),
    },
    feature_plans: [
      {
        id: generateId(),
        title: 'Milestone 1: Habit Categories & Tags',
        status: 'completed',
        milestones: [
          { title: 'Add category pill selectors to UI', status: 'completed' },
          { title: 'Persist category enum in PostgreSQL', status: 'completed' },
        ],
      },
    ],
    journeys: [
      {
        id: generateId(),
        title: 'Authenticated Daily Check-in',
        status: 'passed',
        steps: 4,
        checked_at: new Date(Date.now() - 3600000).toISOString(),
      },
    ],
    active_run: null,
    active_run_kind: null,
    files,
  };

  projects.set(id, initialProject);
  return initialProject;
}

// Seed initial project on boot
seedInitialProject();

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(cors());
  app.use(express.json({ limit: '50mb' }));
  app.use(express.urlencoded({ extended: true, limit: '50mb' }));
  app.use(express.raw({ type: 'application/octet-stream', limit: '50mb' }));

  // API Config
  app.get('/api/config', (req: Request, res: Response) => {
    res.json({
      providers: {
        anthropic: {
          model: 'claude-3-7-sonnet-20250219',
          configured: true,
          limits: {
            budget_usd: 2.0,
            max_input_tokens: 180000,
            max_output_tokens: 24000,
            input_rate: 3.0,
            output_rate: 15.0,
            pricing_known: true,
          },
        },
        openai: {
          model: 'gpt-4o',
          configured: true,
          limits: {
            budget_usd: 2.0,
            max_input_tokens: 128000,
            max_output_tokens: 16384,
            input_rate: 2.5,
            output_rate: 10.0,
            pricing_known: true,
          },
        },
        local: {
          model: 'local-model',
          configured: true,
          limits: {
            budget_usd: 0.0,
            max_input_tokens: 32000,
            max_output_tokens: 8192,
            input_rate: 0.0,
            output_rate: 0.0,
            pricing_known: true,
          },
        },
      },
      version: '0.10.1',
      runtime: {
        system: 'Linux',
        release: '6.6',
        machine: 'x86_64',
        python: '3.10.12',
        wsl: false,
        wsl2: false,
        label: 'AI Studio Linux Runtime',
      },
      local_vision: true,
      offline_only: false,
      documents_folder: '/data/documents',
      files_folder: '/data/files',
      docker_installed: true,
      github_installed: true,
    });
  });

  // Diagnostics
  app.get('/api/diagnostics', (req: Request, res: Response) => {
    res.json({
      platform: {
        system: 'Linux',
        release: '6.6',
        machine: 'x86_64',
        python: '3.10.12',
        wsl: false,
        wsl2: false,
        label: 'AI Studio Linux Runtime',
      },
      offline_only: false,
      offline_readiness: {
        ready: true,
        blockers: [],
        note: 'AI Studio container initialized. Builder environment verified and ready.',
      },
      disk_free_bytes: 107374182400,
      checks: {
        python: { status: 'passed', detail: 'Python 3.10.12' },
        node: { status: 'passed', detail: 'Node.js ' + process.version },
        docker: { status: 'passed', detail: 'Container runtime ready' },
        compose: { status: 'passed', detail: 'Docker Compose v2.27' },
        github: { status: 'passed', detail: 'GitHub CLI active' },
        ocr: { status: 'passed', detail: 'Tesseract OCR available' },
        web_image: { status: 'passed', detail: 'local-foundry-web:2 cached' },
        api_image: { status: 'passed', detail: 'local-foundry-api:2 cached' },
        accounts_image: { status: 'passed', detail: 'local-foundry-accounts:2 cached' },
        database_image: { status: 'passed', detail: 'postgres:17-bookworm cached' },
        browser_image: { status: 'passed', detail: 'playwright-browser cached' },
        builder_database: { status: 'passed', detail: 'connected (in-memory persistent state)' },
        storage: { status: 'passed', detail: 'Storage read/write verified' },
        local_ai: { status: 'passed', detail: 'Providers configured and ready' },
      },
    });
  });

  // List projects
  app.get('/api/projects', (req: Request, res: Response) => {
    const list = Array.from(projects.values()).map(p => ({
      id: p.id,
      name: p.name,
      created_at: p.created_at,
      repo: p.repo,
      preview_url: p.preview_url,
    }));
    res.json(list);
  });

  // Create project
  app.post('/api/projects', (req: Request, res: Response) => {
    const { name, profile = 'starter' } = req.body;
    if (!name || !name.trim()) {
      res.status(400).json({ detail: 'Give the project a name.' });
      return;
    }
    const id = generateId();
    const files = createDefaultFiles(name.trim(), profile);
    const digest = computeDigest(files);

    const project: Project = {
      id,
      name: name.trim(),
      profile,
      created_at: new Date().toISOString(),
      repo: null,
      preview_url: `/api/projects/${id}/preview-frame`,
      sync_state: {},
      last_validation: {
        status: 'passed',
        source_digest: digest,
        gate_version: 6,
        checked_at: new Date().toISOString(),
      },
      source_digest: digest,
      messages: [],
      versions: [
        {
          id: generateId(),
          project_id: id,
          label: 'Starting template',
          digest,
          created_at: new Date().toISOString(),
        },
      ],
      backups: [],
      file_plans: [],
      documents: { status: 'indexed', count: 0 },
      recovery_exports: [],
      dependency_requests: [],
      visual_checks: [],
      context: {
        body: {
          requirements: `Initial setup for ${name}.`,
          architecture: 'React + FastAPI + PostgreSQL template.',
          data_model: 'Initial starter schemas.',
          decisions: 'Adopted standard foundry blueprint.',
          questions: 'What features to implement next?',
        },
        revision: 0,
        agent_notes: 'Initial workspace created.',
        updated_at: new Date().toISOString(),
      },
      feature_plans: [],
      journeys: [],
      active_run: null,
      active_run_kind: null,
      files,
    };

    projects.set(id, project);
    res.status(201).json(project);
  });

  // Project details
  app.get('/api/projects/:id', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    res.json(project);
  });

  // Project files listing
  app.get('/api/projects/:id/files', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const list = Object.keys(project.files).map(filePath => ({
      path: filePath,
      size: Buffer.byteLength(project.files[filePath], 'utf-8'),
      modified: project.created_at,
    }));
    res.json(list);
  });

  // Inspect individual file
  app.get('/api/projects/:id/file', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const filePath = req.query.path as string;
    const content = project.files[filePath] ?? '';
    const ext = path.extname(filePath);
    const language = ext === '.jsx' || ext === '.js' ? 'javascript' : ext === '.py' ? 'python' : ext === '.sql' ? 'sql' : ext === '.css' ? 'css' : 'text';
    res.json({
      path: filePath,
      content,
      lines: content.split('\n').length,
      language,
    });
  });

  // Code search
  app.get('/api/projects/:id/code-search', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const q = (req.query.q as string || '').toLowerCase();
    const results: Array<{ path: string; line: number; text: string }> = [];
    if (q) {
      for (const [filePath, content] of Object.entries(project.files)) {
        const lines = content.split('\n');
        lines.forEach((lineText, idx) => {
          if (lineText.toLowerCase().includes(q)) {
            results.push({ path: filePath, line: idx + 1, text: lineText.trim() });
          }
        });
      }
    }
    res.json(results);
  });

  // Update context
  app.post('/api/projects/:id/context', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { body, revision } = req.body;
    project.context.body = body;
    project.context.revision = (revision ?? project.context.revision) + 1;
    project.context.updated_at = new Date().toISOString();
    res.json(project.context);
  });

  // Create feature plan
  app.post('/api/projects/:id/plans', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { title, milestones } = req.body;
    const plan = {
      id: generateId(),
      title,
      milestones: milestones || [],
      status: 'ready',
      created_at: new Date().toISOString(),
    };
    project.feature_plans.push(plan);
    res.json(plan);
  });

  // Start plan
  app.post('/api/projects/:id/plans/:plan_id/start', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const runId = generateId();
    const run: Run = {
      id: runId,
      project_id: project.id,
      kind: 'milestones',
      status: 'completed',
      created_at: new Date().toISOString(),
      events: [
        { id: nextEventId++, kind: 'status', text: 'Executing milestone plan...', timestamp: new Date().toISOString() },
        { id: nextEventId++, kind: 'event', text: 'Applying database migrations and component updates', timestamp: new Date().toISOString() },
        { id: nextEventId++, kind: 'status', text: 'Milestone execution completed successfully.', timestamp: new Date().toISOString() },
      ],
      usage: {
        input_tokens: 1200,
        output_tokens: 380,
        requests: 1,
        retries: 0,
        estimated_usd: 0.009,
        limits: {
          budget_usd: 2.0,
          max_input_tokens: 180000,
          max_output_tokens: 24000,
          input_rate: 3.0,
          output_rate: 15.0,
        },
      },
    };
    runs.set(runId, run);
    res.json({ run_id: runId, kind: 'milestones' });
  });

  // Start build
  app.post('/api/projects/:id/build', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { prompt, mode = 'coder' } = req.body;
    if (!prompt || !prompt.trim()) {
      res.status(400).json({ detail: 'Prompt cannot be empty.' });
      return;
    }

    const runId = generateId();

    // Record user message
    project.messages.push({
      id: nextMessageId++,
      role: 'user',
      content: prompt.trim(),
      created_at: new Date().toISOString(),
      mode,
    });

    // Simulate build events and code changes
    const newVersionId = generateId();
    const eventTime = new Date().toISOString();

    // Minor code update in project to reflect prompt
    if (project.files['frontend/src/App.jsx']) {
      project.files['frontend/src/App.jsx'] = project.files['frontend/src/App.jsx'].replace(
        /Build a habit journal/,
        `Habit Journal — Updated: ${prompt.trim().slice(0, 40)}`
      );
    }
    project.source_digest = computeDigest(project.files);

    project.versions.unshift({
      id: newVersionId,
      project_id: project.id,
      label: `Built: ${prompt.trim().slice(0, 36)}`,
      digest: project.source_digest,
      created_at: eventTime,
    });

    // Assistant response
    project.messages.push({
      id: nextMessageId++,
      role: 'assistant',
      content: `I've implemented your request: "${prompt.trim()}". The components have been updated and validation checks passed cleanly.`,
      created_at: new Date().toISOString(),
      mode,
    });

    const run: Run = {
      id: runId,
      project_id: project.id,
      kind: 'build',
      status: 'completed',
      created_at: eventTime,
      events: [
        { id: nextEventId++, kind: 'status', text: 'Analyzing project codebase and prompt requirements...', timestamp: eventTime },
        { id: nextEventId++, kind: 'event', text: 'Updating frontend components and application state...', timestamp: eventTime },
        { id: nextEventId++, kind: 'status', text: 'Running automated browser checks and lint verification...', timestamp: eventTime },
        { id: nextEventId++, kind: 'preview', text: 'Preview updated successfully.', url: project.preview_url || undefined, timestamp: eventTime },
      ],
      usage: {
        input_tokens: 3420,
        output_tokens: 890,
        requests: 1,
        retries: 0,
        estimated_usd: 0.023,
        limits: {
          budget_usd: 2.0,
          max_input_tokens: 180000,
          max_output_tokens: 24000,
          input_rate: 3.0,
          output_rate: 15.0,
        },
      },
    };

    runs.set(runId, run);
    res.json({ run_id: runId, kind: 'build' });
  });

  // Run status
  app.get('/api/runs/:run_id', (req: Request, res: Response) => {
    const run = runs.get(req.params.run_id);
    if (!run) {
      res.status(404).json({ detail: 'Run not found.' });
      return;
    }
    const after = parseInt(req.query.after as string || '0', 10);
    const newEvents = run.events.filter(e => e.id > after);
    res.json({
      id: run.id,
      project_id: run.project_id,
      kind: run.kind,
      status: run.status,
      events: newEvents,
      usage: run.usage,
      more: false,
    });
  });

  // Cancel run
  app.post('/api/runs/:run_id/cancel', (req: Request, res: Response) => {
    const run = runs.get(req.params.run_id);
    if (run) {
      run.status = 'cancelled';
    }
    res.json({ message: 'Operation cancelled.' });
  });

  // Preview operations
  app.post('/api/projects/:id/preview/:op', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const op = req.params.op;
    if (op === 'start') {
      project.preview_url = `/api/projects/${project.id}/preview-frame`;
    } else {
      project.preview_url = null;
    }
    const runId = generateId();
    const run: Run = {
      id: runId,
      project_id: project.id,
      kind: 'preview',
      status: 'completed',
      created_at: new Date().toISOString(),
      events: [
        {
          id: nextEventId++,
          kind: 'preview',
          text: op === 'start' ? 'Preview ready.' : 'Preview stopped.',
          url: project.preview_url || undefined,
          timestamp: new Date().toISOString(),
        },
      ],
      usage: {
        input_tokens: 0,
        output_tokens: 0,
        requests: 0,
        retries: 0,
        estimated_usd: 0,
        limits: {
          budget_usd: 2.0,
          max_input_tokens: 180000,
          max_output_tokens: 24000,
          input_rate: 0,
          output_rate: 0,
        },
      },
    };
    runs.set(runId, run);
    res.json({ run_id: runId, kind: 'preview' });
  });

  // Preview frame HTML
  app.get('/api/projects/:id/preview-frame', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).send('Project not found');
      return;
    }
    res.send(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${project.name} Preview</title>
  <style>
    :root {
      --bg: #0c100e;
      --card: #151a17;
      --border: #242c27;
      --accent: #10b981;
      --text: #f0fdf4;
      --muted: #7d9688;
    }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 32px 20px;
      display: flex;
      justify-content: center;
    }
    .container {
      width: 100%;
      max-width: 580px;
    }
    .badge {
      display: inline-block;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      background: rgba(16, 185, 129, 0.15);
      color: var(--accent);
      padding: 4px 10px;
      border-radius: 9999px;
      margin-bottom: 12px;
    }
    h1 {
      margin: 0 0 6px 0;
      font-size: 26px;
      letter-spacing: -0.02em;
    }
    p.desc {
      margin: 0 0 24px 0;
      color: var(--muted);
      font-size: 14px;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-bottom: 24px;
    }
    .stat {
      background: var(--card);
      border: 1px solid var(--border);
      padding: 14px;
      border-radius: 10px;
    }
    .stat .val {
      font-size: 20px;
      font-weight: 700;
    }
    .stat .lbl {
      font-size: 11px;
      color: var(--muted);
      margin-top: 4px;
    }
    .input-row {
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
    }
    input {
      flex: 1;
      background: var(--card);
      border: 1px solid var(--border);
      padding: 12px 14px;
      border-radius: 8px;
      color: var(--text);
      outline: none;
      font-size: 14px;
    }
    input:focus { border-color: var(--accent); }
    button.btn {
      background: var(--accent);
      color: #064e3b;
      border: none;
      font-weight: 600;
      padding: 0 18px;
      border-radius: 8px;
      cursor: pointer;
    }
    .list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .item {
      background: var(--card);
      border: 1px solid var(--border);
      padding: 14px 16px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
    }
    .check {
      width: 20px;
      height: 20px;
      border: 2px solid var(--border);
      border-radius: 5px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      color: var(--accent);
    }
    .item.done { opacity: 0.6; }
    .item.done .check {
      background: rgba(16, 185, 129, 0.2);
      border-color: var(--accent);
    }
    .item.done span.title { text-decoration: line-through; }
    .title { flex: 1; font-size: 14px; }
    .streak { font-size: 12px; color: var(--muted); }
  </style>
</head>
<body>
  <div class="container">
    <span class="badge">Live Preview Sandbox</span>
    <h1>${project.name}</h1>
    <p class="desc">Interactive container sandbox preview running React + PostgreSQL mock.</p>

    <div class="stats">
      <div class="stat"><div class="val" id="completed-count">2 / 3</div><div class="lbl">Completed Today</div></div>
      <div class="stat"><div class="val">14 days</div><div class="lbl">Best Streak</div></div>
      <div class="stat"><div class="val">94%</div><div class="lbl">Weekly Score</div></div>
    </div>

    <div class="input-row">
      <input type="text" id="habit-input" placeholder="Add a habit or goal...">
      <button class="btn" id="add-btn">Add</button>
    </div>

    <div class="list" id="habit-list">
      <div class="item done" onclick="toggleItem(this)">
        <div class="check">✓</div>
        <span class="title">Morning focus meditation</span>
        <span class="streak">12 days 🔥</span>
      </div>
      <div class="item" onclick="toggleItem(this)">
        <div class="check"></div>
        <span class="title">Read 30 minutes</span>
        <span class="streak">4 days 🔥</span>
      </div>
      <div class="item done" onclick="toggleItem(this)">
        <div class="check">✓</div>
        <span class="title">Evening workout session</span>
        <span class="streak">8 days 🔥</span>
      </div>
    </div>
  </div>

  <script>
    function toggleItem(el) {
      el.classList.toggle('done');
      const check = el.querySelector('.check');
      check.textContent = el.classList.contains('done') ? '✓' : '';
      updateStats();
    }
    function updateStats() {
      const all = document.querySelectorAll('.item').length;
      const done = document.querySelectorAll('.item.done').length;
      document.getElementById('completed-count').textContent = done + ' / ' + all;
    }
    document.getElementById('add-btn').onclick = function() {
      const input = document.getElementById('habit-input');
      const val = input.value.trim();
      if (!val) return;
      const div = document.createElement('div');
      div.className = 'item';
      div.onclick = function() { toggleItem(div); };
      div.innerHTML = '<div class="check"></div><span class="title">' + val + '</span><span class="streak">1 day 🔥</span>';
      document.getElementById('habit-list').prepend(div);
      input.value = '';
      updateStats();
    };
    document.getElementById('habit-input').onkeydown = function(e) {
      if (e.key === 'Enter') document.getElementById('add-btn').click();
    };
  </script>
</body>
</html>`);
  });

  // Project logs
  app.get('/api/projects/:id/logs', (req: Request, res: Response) => {
    res.json({
      text: `[Local Foundry] Sandbox initialized for ${req.params.id}
[PostgreSQL 17] Database server listening on port 5432
[FastAPI] Application started on http://127.0.0.1:8000
[Vite 6] Preview client live at http://127.0.0.1:5173
[HealthCheck] All 3 containers report healthy status.`,
    });
  });

  // Restore version
  app.post('/api/projects/:id/restore/:version_id', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const version = project.versions.find(v => v.id === req.params.version_id);
    if (!version) {
      res.status(404).json({ detail: 'Version not found.' });
      return;
    }
    const runId = generateId();
    const run: Run = {
      id: runId,
      project_id: project.id,
      kind: 'restore',
      status: 'completed',
      created_at: new Date().toISOString(),
      events: [
        {
          id: nextEventId++,
          kind: 'status',
          text: `Source restored to ${version.label}. Preview ready.`,
          timestamp: new Date().toISOString(),
        },
      ],
      usage: {
        input_tokens: 0,
        output_tokens: 0,
        requests: 0,
        retries: 0,
        estimated_usd: 0,
        limits: {
          budget_usd: 2.0,
          max_input_tokens: 180000,
          max_output_tokens: 24000,
          input_rate: 0,
          output_rate: 0,
        },
      },
    };
    runs.set(runId, run);
    res.json({ run_id: runId, kind: 'restore' });
  });

  // Validate project
  app.post('/api/projects/:id/validate', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const runId = generateId();
    project.last_validation = {
      status: 'passed',
      source_digest: project.source_digest,
      gate_version: 6,
      checked_at: new Date().toISOString(),
    };
    const run: Run = {
      id: runId,
      project_id: project.id,
      kind: 'validation',
      status: 'completed',
      created_at: new Date().toISOString(),
      events: [
        { id: nextEventId++, kind: 'status', text: 'Running automated lint and type validation...', timestamp: new Date().toISOString() },
        { id: nextEventId++, kind: 'event', text: 'Running full integration suite and accessibility audit...', timestamp: new Date().toISOString() },
        { id: nextEventId++, kind: 'status', text: 'All 6 gate checks passed without regressions.', timestamp: new Date().toISOString() },
      ],
      usage: {
        input_tokens: 0,
        output_tokens: 0,
        requests: 0,
        retries: 0,
        estimated_usd: 0,
        limits: {
          budget_usd: 2.0,
          max_input_tokens: 180000,
          max_output_tokens: 24000,
          input_rate: 0,
          output_rate: 0,
        },
      },
    };
    runs.set(runId, run);
    res.json({ run_id: runId, kind: 'validation' });
  });

  // GitHub review
  app.post('/api/projects/:id/github/review', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { name = 'my-foundry-app' } = req.body;
    res.json({
      repo: `github.com/user/${name}`,
      status: 'ready',
      branches: ['main'],
      diff_stats: '+140 -20',
      message: 'Validated and ready for release publish.',
    });
  });

  // Publish to GitHub
  app.post('/api/projects/:id/publish', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { name } = req.body;
    project.repo = `github.com/user/${name || project.name}`;
    project.sync_state = { published_at: new Date().toISOString(), repo: project.repo };
    res.json({ status: 'published', repo: project.repo });
  });

  // Mobile capabilities
  app.get('/api/mobile/capabilities', (req: Request, res: Response) => {
    res.json({
      apk: true,
      aab: true,
      ipa: true,
      targets: ['apk', 'aab', 'ipa'],
      export_methods: ['debugging', 'release-testing', 'app-store-connect'],
    });
  });

  // Mobile builds listing
  app.get('/api/projects/:id/mobile/builds', (req: Request, res: Response) => {
    res.json([
      {
        id: 'mobile-build-1',
        target: 'apk',
        filename: 'app-testing.apk',
        status: 'completed',
        created_at: new Date(Date.now() - 3600000).toISOString(),
        version: '1.0.0',
        build_number: 1,
      },
    ]);
  });

  // Start mobile build
  app.post('/api/projects/:id/mobile/builds', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { target = 'apk', version = '1.0.0', build_number = 1 } = req.body;
    const runId = generateId();
    const run: Run = {
      id: runId,
      project_id: project.id,
      kind: 'mobile_' + target,
      status: 'completed',
      created_at: new Date().toISOString(),
      events: [
        { id: nextEventId++, kind: 'status', text: `Assembling mobile ${target.toUpperCase()} artifact...`, timestamp: new Date().toISOString() },
        { id: nextEventId++, kind: 'status', text: 'Signing package with development keystore...', timestamp: new Date().toISOString() },
        { id: nextEventId++, kind: 'status', text: `Artifact ready: app-${version}.${target}`, timestamp: new Date().toISOString() },
      ],
      usage: {
        input_tokens: 0,
        output_tokens: 0,
        requests: 0,
        retries: 0,
        estimated_usd: 0,
        limits: {
          budget_usd: 2.0,
          max_input_tokens: 180000,
          max_output_tokens: 24000,
          input_rate: 0,
          output_rate: 0,
        },
      },
    };
    runs.set(runId, run);
    res.status(202).json({ run_id: runId, kind: 'mobile_' + target });
  });

  // Mobile build download
  app.get('/api/projects/:id/mobile/builds/:build_id/download', (req: Request, res: Response) => {
    res.setHeader('Content-Disposition', 'attachment; filename="app-testing.apk"');
    res.setHeader('Content-Type', 'application/vnd.android.package-archive');
    res.send(Buffer.from('MOCK_APK_BINARY_CONTENT'));
  });

  // Mobile build log
  app.get('/api/projects/:id/mobile/builds/:build_id/log', (req: Request, res: Response) => {
    res.json({
      log: `[Capacitor] Building Android package
[Gradle] Task :app:assembleDebug SUCCESSFUL
[Signer] Signed with debug keystore
Artifact verified and packed.`,
    });
  });

  // Download project as ZIP
  app.get('/api/projects/:id/download', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }

    const archive = archiver('zip', { zlib: { level: 9 } });
    res.setHeader('Content-Type', 'application/zip');
    res.setHeader('Content-Disposition', `attachment; filename="${project.name.replace(/[^a-z0-9-]/gi, '-')}.zip"`);

    archive.pipe(res);
    for (const [filePath, fileContent] of Object.entries(project.files)) {
      archive.append(fileContent, { name: filePath });
    }
    archive.finalize();
  });

  // Recovery export
  app.post('/api/projects/:id/recovery', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const item = {
      id: generateId(),
      filename: `${project.name}-recovery.enc`,
      created_at: new Date().toISOString(),
      bytes: 2048,
    };
    project.recovery_exports.push(item);
    res.json(item);
  });

  // Recovery download
  app.get('/api/projects/:id/recovery/:item_id', (req: Request, res: Response) => {
    res.setHeader('Content-Disposition', 'attachment; filename="recovery.enc"');
    res.setHeader('Content-Type', 'application/octet-stream');
    res.send(Buffer.from('ENCRYPTED_RECOVERY_ARCHIVE_MOCK_PAYLOAD'));
  });

  // Recovery import
  app.post('/api/recovery/import', (req: Request, res: Response) => {
    res.json({ status: 'imported', message: 'Recovery archive unpacked.' });
  });

  // Vite dev server mounting or static dist serving
  const isProduction = process.env.NODE_ENV === 'production';
  if (!isProduction) {
    const vite = await createViteServer({
      server: { middlewareMode: true, host: '0.0.0.0' },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.resolve(process.cwd(), 'dist');
    if (fs.existsSync(distPath)) {
      app.use(express.static(distPath));
      app.get('*', (req: Request, res: Response) => {
        res.sendFile(path.join(distPath, 'index.html'));
      });
    }
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Local Foundry running on http://0.0.0.0:${PORT}`);
  });
}

startServer().catch(err => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
