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

interface AgentNote {
  text: string;
  at: string;
}

interface ProjectContext {
  body: {
    requirements: string;
    architecture: string;
    data_model: string;
    decisions: string;
    open_questions: string;
    [key: string]: string | undefined;
  };
  revision: number;
  agent_notes: AgentNote[];
  updated_at: string;
}

interface EnvVariable {
  key: string;
  value: string;
  scope: string;
  description?: string;
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
  env_vars: EnvVariable[];
  mobile_builds?: any[];
}

function formatRawEnv(vars: EnvVariable[] = []): string {
  return vars
    .map(v => `# ${v.description || v.scope}\n${v.key}=${v.value}`)
    .join('\n\n');
}

function escapeXml(unsafe: string): string {
  return String(unsafe || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function generateScreenshotSvg(projectName: string, reqPath: string, viewport: 'desktop' | 'mobile'): string {
  const isMobile = viewport === 'mobile';
  const width = isMobile ? 390 : 1280;
  const height = isMobile ? 844 : 800;

  if (isMobile) {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
      <rect width="100%" height="100%" fill="#0c140e"/>
      <!-- Mobile Top Bar -->
      <rect width="100%" height="44" fill="#111c14"/>
      <text x="24" y="28" fill="#e2fae7" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="14" font-weight="600">9:41</text>
      <circle cx="340" cy="24" r="3" fill="#8da491"/>
      <rect x="348" y="19" width="22" height="11" rx="3" fill="none" stroke="#8da491" stroke-width="1.5"/>
      <rect x="350" y="21" width="14" height="7" rx="1.5" fill="#8da491"/>
      <!-- App Header -->
      <rect y="44" width="100%" height="60" fill="#142218" stroke="#253a2a" stroke-width="1"/>
      <text x="20" y="80" fill="#dbedd6" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="18" font-weight="700">${escapeXml(projectName)}</text>
      <text x="20" y="96" fill="#75937a" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="11">Route: ${escapeXml(reqPath)}</text>
      <!-- Mobile Content Cards -->
      <g transform="translate(16, 120)">
        <!-- Card 1 -->
        <rect width="358" height="110" rx="12" fill="#16271c" stroke="#2d4834" stroke-width="1"/>
        <circle cx="36" cy="36" r="14" fill="#2d5e3c"/>
        <text x="31" y="41" fill="#4ade80" font-size="16">✓</text>
        <text x="64" y="34" fill="#f0fbf2" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="16" font-weight="600">Morning Meditation</text>
        <text x="64" y="52" fill="#88a58f" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">15 mins mindfulness · 14 day streak</text>
        <rect x="64" y="68" width="270" height="6" rx="3" fill="#0f1911"/>
        <rect x="64" y="68" width="230" height="6" rx="3" fill="#4ade80"/>
        <text x="64" y="92" fill="#698570" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="10">85% consistency this month</text>

        <!-- Card 2 -->
        <g transform="translate(0, 126)">
          <rect width="358" height="110" rx="12" fill="#16271c" stroke="#2d4834" stroke-width="1"/>
          <circle cx="36" cy="36" r="14" fill="#2d5e3c"/>
          <text x="31" y="41" fill="#4ade80" font-size="16">✓</text>
          <text x="64" y="34" fill="#f0fbf2" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="16" font-weight="600">30-Min Cardio / Run</text>
          <text x="64" y="52" fill="#88a58f" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">Outdoor track · 7 day streak</text>
          <rect x="64" y="68" width="270" height="6" rx="3" fill="#0f1911"/>
          <rect x="64" y="68" width="180" height="6" rx="3" fill="#38bdf8"/>
          <text x="64" y="92" fill="#698570" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="10">72% consistency this month</text>
        </g>

        <!-- Card 3 -->
        <g transform="translate(0, 252)">
          <rect width="358" height="110" rx="12" fill="#16271c" stroke="#2d4834" stroke-width="1"/>
          <circle cx="36" cy="36" r="14" fill="#223628"/>
          <text x="64" y="34" fill="#d1e3ce" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="16" font-weight="600">Deep Work Session (2h)</text>
          <text x="64" y="52" fill="#88a58f" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">Focused code delivery</text>
          <rect x="64" y="68" width="270" height="6" rx="3" fill="#0f1911"/>
          <rect x="64" y="68" width="90" height="6" rx="3" fill="#fbbf24"/>
          <text x="64" y="92" fill="#698570" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="10">Scheduled for 2:00 PM</text>
        </g>
      </g>
      <!-- Mobile Bottom Tab Bar -->
      <rect y="${height - 64}" width="100%" height="64" fill="#111c14" stroke="#253a2a" stroke-width="1"/>
      <circle cx="70" cy="${height - 36}" r="8" fill="#4ade80"/>
      <circle cx="195" cy="${height - 36}" r="8" fill="#45604b"/>
      <circle cx="320" cy="${height - 36}" r="8" fill="#45604b"/>
    </svg>`;
  }

  // Desktop
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
    <rect width="100%" height="100%" fill="#0a120c"/>
    <!-- Desktop Browser Chrome Header -->
    <rect width="100%" height="42" fill="#142017" stroke="#233526" stroke-width="1"/>
    <circle cx="20" cy="21" r="5.5" fill="#ef4444"/>
    <circle cx="36" cy="21" r="5.5" fill="#f59e0b"/>
    <circle cx="52" cy="21" r="5.5" fill="#10b981"/>
    <!-- Address Bar -->
    <rect x="180" y="8" width="700" height="26" rx="6" fill="#0a120c" stroke="#253a2a" stroke-width="1"/>
    <text x="200" y="25" fill="#88a38d" font-family="ui-monospace, monospace" font-size="12">http://localhost:5173${escapeXml(reqPath)}</text>
    <!-- App Navbar -->
    <rect y="42" width="100%" height="56" fill="#111d14" stroke="#223626" stroke-width="1"/>
    <text x="32" y="76" fill="#e0f2dc" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="18" font-weight="700">${escapeXml(projectName)}</text>
    <rect x="1100" y="54" width="140" height="32" rx="6" fill="#245435"/>
    <text x="1132" y="74" fill="#f0fdf4" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="13" font-weight="600">+ New Habit</text>
    <!-- Main Dashboard Viewport Content -->
    <g transform="translate(32, 120)">
      <!-- Metric Cards -->
      <g>
        <rect width="280" height="110" rx="10" fill="#142217" stroke="#273e2d" stroke-width="1"/>
        <text x="24" y="36" fill="#7d9b83" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12" font-weight="600">ACTIVE STREAK</text>
        <text x="24" y="78" fill="#4ade80" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="34" font-weight="800">14 Days</text>
      </g>
      <g transform="translate(305, 0)">
        <rect width="280" height="110" rx="10" fill="#142217" stroke="#273e2d" stroke-width="1"/>
        <text x="24" y="36" fill="#7d9b83" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12" font-weight="600">COMPLETION RATE</text>
        <text x="24" y="78" fill="#60a5fa" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="34" font-weight="800">92.4%</text>
      </g>
      <g transform="translate(610, 0)">
        <rect width="280" height="110" rx="10" fill="#142217" stroke="#273e2d" stroke-width="1"/>
        <text x="24" y="36" fill="#7d9b83" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12" font-weight="600">TOTAL SESSIONS</text>
        <text x="24" y="78" fill="#fbbf24" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="34" font-weight="800">184</text>
      </g>
      <g transform="translate(915, 0)">
        <rect width="300" height="110" rx="10" fill="#142217" stroke="#273e2d" stroke-width="1"/>
        <text x="24" y="36" fill="#7d9b83" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12" font-weight="600">SECURITY &amp; VALIDATION</text>
        <text x="24" y="74" fill="#a7f3d0" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="20" font-weight="700">✓ Verified</text>
      </g>
      <!-- Main Content Table / List -->
      <g transform="translate(0, 140)">
        <rect width="1215" height="460" rx="10" fill="#121e15" stroke="#253a29" stroke-width="1"/>
        <text x="28" y="40" fill="#d9ecce" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="17" font-weight="700">Today's Habits &amp; Routines</text>
        <!-- Rows -->
        <line x1="28" y1="62" x2="1187" y2="62" stroke="#233626" stroke-width="1"/>
        <rect x="28" y="80" width="1159" height="74" rx="8" fill="#17271c" stroke="#2e4835" stroke-width="1"/>
        <circle cx="56" cy="117" r="14" fill="#2d5e3c"/>
        <text x="51" y="122" fill="#4ade80" font-size="16">✓</text>
        <text x="84" y="114" fill="#ecfdf5" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="15" font-weight="600">Morning Meditation &amp; Mindfulness</text>
        <text x="84" y="132" fill="#8ba891" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">15 minutes breathing exercise · Category: Wellness</text>
        <rect x="1060" y="102" width="100" height="30" rx="6" fill="#23422e"/>
        <text x="1080" y="122" fill="#bbf7d0" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">Completed</text>

        <rect x="28" y="168" width="1159" height="74" rx="8" fill="#17271c" stroke="#2e4835" stroke-width="1"/>
        <circle cx="56" cy="205" r="14" fill="#2d5e3c"/>
        <text x="51" y="210" fill="#4ade80" font-size="16">✓</text>
        <text x="84" y="202" fill="#ecfdf5" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="15" font-weight="600">30-Min High Intensity Cardio / Outdoor Run</text>
        <text x="84" y="220" fill="#8ba891" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">Track distance and heart-rate recovery · Category: Fitness</text>
        <rect x="1060" y="190" width="100" height="30" rx="6" fill="#23422e"/>
        <text x="1080" y="210" fill="#bbf7d0" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">Completed</text>

        <rect x="28" y="256" width="1159" height="74" rx="8" fill="#17271c" stroke="#2e4835" stroke-width="1"/>
        <circle cx="56" cy="293" r="14" fill="#1d3123"/>
        <text x="84" y="290" fill="#ecfdf5" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="15" font-weight="600">Deep Work Programming Session</text>
        <text x="84" y="308" fill="#8ba891" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">2 hours uninterrupted system design · Category: Career</text>
        <rect x="1060" y="278" width="100" height="30" rx="6" fill="#1c3022"/>
        <text x="1084" y="298" fill="#93af98" font-family="-apple-system, BlinkMacSystemFont, sans-serif" font-size="12">Pending</text>
      </g>
    </g>
  </svg>`;
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
        id: 'vis_desktop_1',
        viewport: 'desktop',
        path: '/',
        status: 'passed',
        source_digest: 'initial',
        created_at: new Date(Date.now() - 3600000 * 1.5).toISOString(),
        title: 'Habit Tracker · Desktop (1280×800)',
        horizontal_overflow: false,
        actions: [{ action: 'visible', selector: 'h1', value: '' }],
        errors: [],
        failed_requests: [],
      },
      {
        id: 'vis_mobile_1',
        viewport: 'mobile',
        path: '/',
        status: 'passed',
        source_digest: 'initial',
        created_at: new Date(Date.now() - 3600000 * 1.2).toISOString(),
        title: 'Habit Tracker · Mobile (390×844)',
        horizontal_overflow: false,
        actions: [{ action: 'visible', selector: '.card', value: '' }],
        errors: [],
        failed_requests: [],
      },
    ],
    context: {
      body: {
        requirements: 'Daily habit tracking with persistence, streaks, and weekly statistics.',
        architecture: 'React frontend with dark mode palette, FastAPI REST endpoints, and PostgreSQL schema.',
        data_model: 'habits table with id, title, completed, streak, and timestamp fields.',
        decisions: 'Local storage caching with backend sync on change.',
        open_questions: 'Add category tags or multi-user accounts in next release?',
      },
      revision: 1,
      agent_notes: [
        {
          text: 'Components are organized cleanly in frontend/src with CSS variables.',
          at: new Date(Date.now() - 3600000).toISOString(),
        },
      ],
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
    env_vars: [
      { key: 'APP_ENV', value: 'development', scope: 'runtime', description: 'Application target environment' },
      { key: 'PORT', value: '5173', scope: 'runtime', description: 'Container web server port' },
      { key: 'DATABASE_URL', value: 'postgresql://app:preview-only@db:5432/app', scope: 'runtime', description: 'PostgreSQL connection URL' },
      { key: 'LOG_LEVEL', value: 'debug', scope: 'runtime', description: 'Logger verbosity level' },
      { key: 'CORS_ALLOWED_ORIGINS', value: 'http://localhost:3000', scope: 'runtime', description: 'Allowed origins for CORS' },
      { key: 'FASTAPI_DEBUG', value: '1', scope: 'runtime', description: 'FastAPI debug mode' },
    ],
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
          open_questions: 'What features to implement next?',
        },
        revision: 0,
        agent_notes: [
          {
            text: 'Initial workspace created with starter schemas.',
            at: new Date().toISOString(),
          },
        ],
        updated_at: new Date().toISOString(),
      },
      feature_plans: [],
      journeys: [],
      active_run: null,
      active_run_kind: null,
      files,
      env_vars: [
        { key: 'APP_ENV', value: 'development', scope: 'runtime', description: 'Application target environment' },
        { key: 'PORT', value: '5173', scope: 'runtime', description: 'Container web server port' },
        { key: 'DATABASE_URL', value: 'postgresql://app:preview-only@db:5432/app', scope: 'runtime', description: 'PostgreSQL connection URL' },
        { key: 'LOG_LEVEL', value: 'info', scope: 'runtime', description: 'Logger verbosity level' },
      ],
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

  // Environment variables endpoints
  app.get('/api/projects/:id/env', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    res.json({
      variables: project.env_vars || [],
      raw: formatRawEnv(project.env_vars || []),
    });
  });

  app.post('/api/projects/:id/env', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { variables, key, value, scope = 'runtime', description } = req.body;
    if (Array.isArray(variables)) {
      project.env_vars = variables;
    } else if (key) {
      const cleanKey = String(key).trim().toUpperCase().replace(/[^A-Z0-9_]/g, '_');
      const existing = (project.env_vars || []).filter(v => v.key !== cleanKey);
      existing.push({
        key: cleanKey,
        value: String(value ?? ''),
        scope: String(scope),
        description: description ? String(description) : undefined,
      });
      project.env_vars = existing;
    }
    project.files['.env'] = formatRawEnv(project.env_vars);
    project.source_digest = computeDigest(project.files);
    res.json({
      variables: project.env_vars,
      raw: formatRawEnv(project.env_vars),
    });
  });

  app.delete('/api/projects/:id/env/:key', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const targetKey = req.params.key.toUpperCase();
    project.env_vars = (project.env_vars || []).filter(v => v.key !== targetKey);
    project.files['.env'] = formatRawEnv(project.env_vars);
    project.source_digest = computeDigest(project.files);
    res.json({
      variables: project.env_vars,
      raw: formatRawEnv(project.env_vars),
    });
  });

  // Project files listing
  app.get('/api/projects/:id/files', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    if (req.query.format === 'details') {
      const list = Object.keys(project.files).map(filePath => ({
        path: filePath,
        size: Buffer.byteLength(project.files[filePath], 'utf-8'),
        modified: project.created_at,
      }));
      res.json(list);
    } else {
      res.json(Object.keys(project.files));
    }
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
    project.context.body = { ...project.context.body, ...body };
    project.context.revision = (revision ?? project.context.revision) + 1;
    project.context.updated_at = new Date().toISOString();
    if (!Array.isArray(project.context.agent_notes)) {
      project.context.agent_notes = [];
    }
    project.context.agent_notes.unshift({
      text: `Context revision ${project.context.revision} updated.`,
      at: new Date().toISOString(),
    });
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

  // Run browser visual check
  app.post('/api/projects/:id/visual', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { path: checkPath = '/', viewport = 'desktop', actions = [] } = req.body;
    const runId = generateId();
    const checkId = generateId();
    const eventTime = new Date().toISOString();

    const newCheck = {
      id: checkId,
      viewport: viewport === 'mobile' ? 'mobile' : 'desktop',
      path: String(checkPath || '/'),
      status: 'passed',
      source_digest: project.source_digest,
      created_at: eventTime,
      title: `${project.name} · ${viewport === 'mobile' ? 'Mobile (390×844)' : 'Desktop (1280×800)'}`,
      horizontal_overflow: false,
      actions: Array.isArray(actions) ? actions : [],
      errors: [],
      failed_requests: [],
    };

    if (!Array.isArray(project.visual_checks)) {
      project.visual_checks = [];
    }
    project.visual_checks.unshift(newCheck);

    const run: Run = {
      id: runId,
      project_id: project.id,
      kind: 'visual',
      status: 'completed',
      created_at: eventTime,
      events: [
        { id: nextEventId++, kind: 'status', text: `Spinning up headless browser container for ${viewport} viewport...`, timestamp: eventTime },
        { id: nextEventId++, kind: 'event', text: `Navigating to internal preview endpoint "${checkPath}"...`, timestamp: eventTime },
        { id: nextEventId++, kind: 'status', text: 'Inspecting layout tree, viewport overflow boundaries, and rendering stability...', timestamp: eventTime },
        { id: nextEventId++, kind: 'preview', text: `Snapshot captured successfully for ${viewport} viewport. 0 regressions.`, timestamp: eventTime },
      ],
      usage: {
        input_tokens: 0,
        output_tokens: 0,
        requests: 1,
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
    res.json({ run_id: runId, kind: 'visual', check: newCheck });
  });

  // Get visual screenshot image
  app.get('/api/projects/:id/visual/:visualId', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const check = (project.visual_checks || []).find((c: any) => c.id === req.params.visualId);
    const viewport = check?.viewport === 'mobile' ? 'mobile' : 'desktop';
    const checkPath = check?.path || '/';
    const svg = generateScreenshotSvg(project.name, checkPath, viewport);

    res.setHeader('Content-Type', 'image/svg+xml');
    res.setHeader('Cache-Control', 'no-cache');
    res.send(svg);
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
      apk: {
        available: true,
        blockers: [],
      },
      aab: {
        available: true,
        blockers: [],
      },
      ipa: {
        available: true,
        blockers: [],
      },
      targets: ['apk', 'aab', 'ipa'],
      export_methods: ['debugging', 'release-testing', 'app-store-connect'],
    });
  });

  // Mobile builds listing
  app.get('/api/projects/:id/mobile/builds', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    if (!project.mobile_builds) {
      project.mobile_builds = [
        {
          id: 'mobile-build-1',
          project_id: project.id,
          target: 'apk',
          filename: `${project.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}-debug.apk`,
          status: 'completed',
          created_at: new Date(Date.now() - 3600000).toISOString(),
          version: '1.0.0',
          build_number: 1,
          origin: project.preview_url || 'http://localhost:3000',
          phase: 'Signed debug APK ready for device sideload testing.',
          bytes: 15420000,
          sha256: 'a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890',
        },
      ];
    }
    res.json(project.mobile_builds);
  });

  // Start mobile build
  app.post('/api/projects/:id/mobile/builds', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    if (!project) {
      res.status(404).json({ detail: 'Project not found.' });
      return;
    }
    const { target = 'apk', version = '1.0.0', build_number = 1, origin } = req.body;
    const runId = generateId();
    const buildId = generateId();
    const eventTime = new Date().toISOString();

    const newBuild = {
      id: buildId,
      project_id: project.id,
      target,
      filename: `${project.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}-v${version}.${target}`,
      status: 'completed',
      created_at: eventTime,
      version: String(version),
      build_number: Number(build_number) || 1,
      origin: origin || project.preview_url || 'https://app.example.com',
      phase: `Signed ${String(target).toUpperCase()} artifact ready for installation.`,
      bytes: target === 'apk' ? 15800000 : target === 'aab' ? 12400000 : 24100000,
      sha256: crypto.createHash('sha256').update(buildId + eventTime).digest('hex'),
    };

    if (!Array.isArray(project.mobile_builds)) {
      project.mobile_builds = [];
    }
    project.mobile_builds.unshift(newBuild);

    const run: Run = {
      id: runId,
      project_id: project.id,
      kind: 'mobile_' + target,
      status: 'completed',
      created_at: eventTime,
      events: [
        { id: nextEventId++, kind: 'status', text: `Assembling mobile ${String(target).toUpperCase()} artifact...`, timestamp: eventTime },
        { id: nextEventId++, kind: 'event', text: `Packaging web view container with assets from ${origin || 'app'}...`, timestamp: eventTime },
        { id: nextEventId++, kind: 'status', text: 'Signing package with development keystore...', timestamp: eventTime },
        { id: nextEventId++, kind: 'preview', text: `Artifact ready: ${newBuild.filename}`, timestamp: eventTime },
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
    res.status(202).json({ run_id: runId, kind: 'mobile_' + target, build: newBuild });
  });

  // Mobile build download
  app.get('/api/projects/:id/mobile/builds/:build_id/download', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    const build = (project?.mobile_builds || []).find((b: any) => b.id === req.params.build_id);
    const filename = build?.filename || 'app-testing.apk';
    const contentType = filename.endsWith('.apk')
      ? 'application/vnd.android.package-archive'
      : filename.endsWith('.aab')
      ? 'application/octet-stream'
      : 'application/octet-stream';
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    res.setHeader('Content-Type', contentType);
    res.send(Buffer.from(`MOCK_MOBILE_PACKAGE_CONTENT_FOR_${filename}`));
  });

  // Mobile build log
  app.get('/api/projects/:id/mobile/builds/:build_id/log', (req: Request, res: Response) => {
    const project = projects.get(req.params.id);
    const build = (project?.mobile_builds || []).find((b: any) => b.id === req.params.build_id);
    const target = build?.target || 'apk';
    res.json({
      log: `[Capacitor] Initializing native ${target.toUpperCase()} platform wrapper
[Gradle] Running assembleRelease with target SDK 34
[Assets] Bundling web app preview assets from ${build?.origin || 'production'}
[Signer] Package signed successfully: ${build?.filename || 'app.apk'}
[Verify] SHA-256 integrity checksum recorded: ${build?.sha256 || 'verified'}
Artifact ready: ${build?.bytes ? (build.bytes / 1024 / 1024).toFixed(1) : '15.2'} MB`,
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
