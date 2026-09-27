import React, { useState } from 'react';
import {
  Sparkles,
  ArrowRight,
  Database,
  Layers,
  Code2,
  CheckCircle,
  Zap,
  Smartphone,
  Shield,
  Upload,
  FolderPlus,
  Terminal,
} from 'lucide-react';
import './emergent-hero.css';

interface EmergentHeroProps {
  onStartProject: (prompt: string, projectName: string) => void;
  onOpenRecovery: () => void;
  isSuperAdmin?: boolean;
  onOpenAdminDashboard?: () => void;
}

const INSPIRATION_PROMPTS = [
  {
    title: 'SaaS Client Portal',
    desc: 'B2B subscription portal with tiered billing, project boards, and PostgreSQL data persistence.',
    prompt: 'Build a modern B2B SaaS client portal with user profiles, project tracking boards, payment status indicators, and clean dark mode UI. Use PostgreSQL for relational storage.',
  },
  {
    title: 'Mobile-First Habit Journal',
    desc: 'Daily habit streaks, progress cards, weekly analytics, and responsive mobile emulator view.',
    prompt: 'Build an everyday habit tracking app with daily check-ins, streak counter, weekly radar chart, and sound feedback. Include responsive mobile views.',
  },
  {
    title: 'AI Codebase Vector Explorer',
    desc: 'Local semantic RAG browser with nomic-embed-text 768-dim embeddings and query audit.',
    prompt: 'Build an AI engineering workbench to inspect local codebase vector embeddings, compute cosine similarities, and monitor token pruning efficiency.',
  },
  {
    title: 'E-Commerce Admin Dashboard',
    desc: 'Inventory catalog, order fulfillment pipeline, customer cohorts, and revenue telemetry.',
    prompt: 'Build a production-grade e-commerce admin dashboard with product inventory tables, order status badges, customer tiers, and revenue analytics.',
  },
];

export default function EmergentHero({
  onStartProject,
  onOpenRecovery,
  isSuperAdmin,
  onOpenAdminDashboard,
}: EmergentHeroProps) {
  const [promptText, setPromptText] = useState('');
  const [selectedStack, setSelectedStack] = useState('fullstack');

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!promptText.trim()) return;

    // Generate smart name from prompt
    const words = promptText.trim().split(/\s+/).slice(0, 4).join(' ');
    const title = words.length > 28 ? `${words.slice(0, 25)}…` : words;
    onStartProject(promptText, title || 'New AI Application');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="emergent-hero-container">
      {/* Top Tagline Pill */}
      <div className="emergent-pill-badge">
        <Sparkles size={14} />
        <span>AGENTIC AI FULL-STACK APP BUILDER</span>
      </div>

      {/* Main Emergent Headline */}
      <h1 className="emergent-title">
        Build software from idea to production
        <br />
        <span className="emergent-title-gradient">in natural language.</span>
      </h1>

      <p className="emergent-subtitle">
        LocalFoundry plans architecture, writes full-stack React and Python code, configures PostgreSQL schemas, and creates production releases — backed by local SQLite codebase RAG.
      </p>

      {/* Central Large Composer Box (emergent.sh style) */}
      <form className="emergent-composer-card" onSubmit={handleSubmit}>
        <textarea
          className="emergent-textarea"
          placeholder="Describe the application you want to build (e.g. 'Build a client portal with Stripe subscriptions, Kanban pipeline, and PostgreSQL database')..."
          value={promptText}
          onChange={(e) => setPromptText(e.target.value)}
          onKeyDown={handleKeyDown}
          autoFocus
        />

        <div className="emergent-composer-bottom">
          <div className="emergent-chips-row">
            <span className="emergent-stack-chip active">
              <Code2 size={12} /> React SPA
            </span>
            <span className="emergent-stack-chip active">
              <Database size={12} /> PostgreSQL
            </span>
            <span className="emergent-stack-chip active">
              <Zap size={12} /> SQLite Vector RAG (-71% tokens)
            </span>
            <span className="emergent-stack-chip">
              <Smartphone size={12} /> Mobile Native
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              className="action-btn-small"
              onClick={onOpenRecovery}
              title="Import recovery snapshot"
              style={{ background: '#17271c', color: '#9bb897', border: '1px solid rgba(255,255,255,0.08)' }}>
              <Upload size={13} /> Import .enc
            </button>

            <button
              type="submit"
              className="emergent-submit-btn"
              disabled={!promptText.trim()}>
              <span>Generate App</span>
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </form>

      {/* Quick Suggestions Cards */}
      <div className="emergent-suggestions-grid">
        {INSPIRATION_PROMPTS.map((item, i) => (
          <div
            key={i}
            className="emergent-suggestion-card"
            onClick={() => {
              setPromptText(item.prompt);
              onStartProject(item.prompt, item.title);
            }}>
            <div className="emergent-suggestion-header">
              <span>{item.title}</span>
              <ArrowRight size={13} color="#10b981" />
            </div>
            <div className="emergent-suggestion-text">{item.desc}</div>
          </div>
        ))}
      </div>

      {/* Bottom Features Strip */}
      <div className="emergent-features-bar">
        <div className="emergent-feature-item">
          <CheckCircle size={15} />
          <span>Full-Stack Code Ownership</span>
        </div>
        <div className="emergent-feature-item">
          <CheckCircle size={15} />
          <span>Autonomous Error Repair</span>
        </div>
        <div className="emergent-feature-item">
          <CheckCircle size={15} />
          <span>PostgreSQL Migrations</span>
        </div>
        <div className="emergent-feature-item">
          <CheckCircle size={15} />
          <span>Live Hot-Reload Sandbox</span>
        </div>
        {isSuperAdmin && onOpenAdminDashboard && (
          <div
            className="emergent-feature-item"
            style={{ cursor: 'pointer', color: '#34d399' }}
            onClick={onOpenAdminDashboard}>
            <Shield size={15} />
            <span>Super Admin Dashboard & Analytics →</span>
          </div>
        )}
      </div>
    </div>
  );
}
