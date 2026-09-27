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
  Check,
  CreditCard,
  ExternalLink,
  ChevronDown,
  HelpCircle,
  Cpu,
  Lock,
  GitBranch,
  Play,
  Globe,
  Sliders,
  DollarSign,
  Star,
} from 'lucide-react';
import './emergent-hero.css';

interface EmergentLandingProps {
  onStartProject: (prompt: string, projectName: string) => void;
  onOpenRecovery: () => void;
  onOpenLogin: () => void;
  user: any;
  isSuperAdmin?: boolean;
  onOpenAdminDashboard?: () => void;
  projects?: Array<{ id: string; name: string }>;
  onSelectProject?: (projectId: string) => void;
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

const PRICING_TIERS = [
  {
    id: 'free',
    name: 'Free Tester',
    tagline: 'Explore conversational AI building and prototypes',
    monthlyPrice: 0,
    annualPrice: 0,
    credits: '10 monthly credits',
    badge: null,
    highlight: false,
    features: [
      '1 Public App Workspace',
      'Conversational React frontend generator',
      'Community template library',
      'SQLite vector index demo',
      'Standard model generation queue',
    ],
    cta: 'Get Started Free',
  },
  {
    id: 'standard',
    name: 'Standard',
    tagline: 'Ideal for independent developers and makers',
    monthlyPrice: 20,
    annualPrice: 17,
    credits: '100 monthly credits',
    badge: 'POPULAR',
    highlight: true,
    features: [
      '10 App Workspaces',
      'PostgreSQL full-stack persistence',
      'Private GitHub repository sync',
      'Local nomic-embed-text RAG (-71% tokens)',
      'Custom subdomains & web preview sandbox',
      'Android APK mobile simulation',
      'Email developer support',
    ],
    cta: 'Start Standard Trial',
  },
  {
    id: 'pro',
    name: 'Pro Builder',
    tagline: 'For fast-growing products & power engineers',
    monthlyPrice: 200,
    annualPrice: 167,
    credits: '750 monthly credits',
    badge: 'POWER',
    highlight: false,
    features: [
      'Unlimited App Workspaces',
      '1M Token Context Window processing',
      'Automated autonomous bug self-healing',
      'Dedicated SQLite vector clusters',
      'Multi-model fallback (Claude, Gemini, Ollama)',
      'Priority build queue & real-time telemetry',
      'Encrypted snapshot cloud backups',
    ],
    cta: 'Upgrade to Pro',
  },
  {
    id: 'team',
    name: 'Team / Enterprise',
    tagline: 'Collaborative workspaces for organizations',
    monthlyPrice: 300,
    annualPrice: 250,
    credits: '1,250 shared credits',
    badge: 'ENTERPRISE',
    highlight: false,
    features: [
      'Multi-seat developer collaboration',
      'Centralized Super Admin tenant dashboard',
      'Custom keystore APK signing & publishing',
      'Self-hosted Ollama private LLM integration',
      'Audit log streams with Firestore persistence',
      '24/7 SLA & dedicated solution engineer',
    ],
    cta: 'Contact Enterprise',
  },
];

const PLATFORM_FEATURES = [
  {
    icon: <Sparkles size={22} color="#10b981" />,
    title: 'Conversational Full-Stack Generation',
    description: 'Describe any feature in English. The agent drafts architecture diagrams, generates type-safe React UI, builds Python API routes, and applies database migrations automatically.',
  },
  {
    icon: <Zap size={22} color="#38bdf8" />,
    title: 'Local Codebase Vector RAG',
    description: 'Integrated SQLite vector engine using nomic-embed-text 768-dim embeddings cuts prompt token consumption by 71% by only injecting relevant symbols into context.',
  },
  {
    icon: <Database size={22} color="#34d399" />,
    title: 'PostgreSQL & Real Relational Storage',
    description: 'No mock data illusions. Every app gets real relational database schemas, Drizzle/SQL migrations, and instant RESTful endpoint scaffolding.',
  },
  {
    icon: <Smartphone size={22} color="#f59e0b" />,
    title: 'Mobile APK & Responsive Emulator',
    description: 'One-click native mobile packaging simulation with instant responsive device previews, touch gestures, and ready-to-deploy release manifests.',
  },
  {
    icon: <Lock size={22} color="#a855f7" />,
    title: 'Autonomous Self-Healing Engine',
    description: 'When runtime errors or compilation breaks occur, the background repair agent captures the trace, patches the AST, and verifies the build automatically.',
  },
  {
    icon: <GitBranch size={22} color="#10b981" />,
    title: '100% Code Ownership & GitHub Sync',
    description: 'Export pristine ZIP archives, sync straight to your GitHub repositories, or download encrypted `.enc` snapshots for total offline continuity.',
  },
];

const FAQS = [
  {
    q: 'How does credit consumption work on LocalFoundary?',
    a: 'Each action that calls the LLM, runs code analysis, generates files, or executes an autonomous repair loop consumes platform credits. Unused credits refresh on your monthly billing cycle.',
  },
  {
    q: 'Do I own the generated source code?',
    a: 'Yes, 100%. All generated TypeScript, Python, and SQL files are entirely yours with zero vendor lock-in. You can download a ZIP file or sync directly to GitHub at any time.',
  },
  {
    q: 'How does the SQLite vector RAG work?',
    a: 'The local codebase vector index breaks down your project files into semantic chunks, creates 768-dimensional embeddings using nomic-embed-text, and retrieves the most relevant symbols to minimize context tokens.',
  },
  {
    q: 'Can I connect my own custom domains and databases?',
    a: 'Yes! LocalFoundary supports external database connections including PostgreSQL, Supabase, Neon, and custom domain routing with automatic SSL provisioning.',
  },
];

export default function EmergentLanding({
  onStartProject,
  onOpenRecovery,
  onOpenLogin,
  user,
  isSuperAdmin,
  onOpenAdminDashboard,
  projects = [],
  onSelectProject,
}: EmergentLandingProps) {
  const [promptText, setPromptText] = useState('');
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'annual'>('monthly');
  const [activeFaq, setActiveFaq] = useState<number | null>(null);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!promptText.trim()) return;

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
    <div className="emergent-landing-page">
      {/* Top Navbar Header */}
      <header className="emergent-landing-navbar">
        <div className="emergent-nav-left">
          <div className="emergent-nav-brand">
            <div className="emergent-nav-logo-icon">
              <Sparkles size={18} />
            </div>
            <span className="emergent-nav-title">LocalFoundary</span>
          </div>
          <nav className="emergent-nav-menu">
            <a href="#features" className="emergent-nav-link">Features</a>
            <a href="#pricing" className="emergent-nav-link">Pricing & Plans</a>
            <a href="#faqs" className="emergent-nav-link">FAQ</a>
            {isSuperAdmin && onOpenAdminDashboard && (
              <button
                type="button"
                onClick={onOpenAdminDashboard}
                className="emergent-nav-link admin-pill-link">
                <Shield size={13} color="#f87171" />
                <span>Super Admin</span>
              </button>
            )}
          </nav>
        </div>

        <div className="emergent-nav-right">
          {user ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <button
                type="button"
                className="emergent-nav-login-btn user-active"
                onClick={onOpenLogin}>
                {user.photoURL ? (
                  <img src={user.photoURL} alt="" style={{ width: '18px', height: '18px', borderRadius: '50%' }} />
                ) : (
                  <Shield size={13} color="#10b981" />
                )}
                <span>{user.displayName?.split(' ')[0] || user.email?.split('@')[0]}</span>
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                type="button"
                className="emergent-nav-login-btn"
                onClick={onOpenLogin}>
                Log in
              </button>
              <button
                type="button"
                className="emergent-nav-signup-btn"
                onClick={onOpenLogin}>
                Sign up free
              </button>
            </div>
          )}
        </div>
      </header>

      {/* 1. Hero Section */}
      <section className="emergent-hero-container">
        {/* Top Tagline Pill */}
        <div className="emergent-pill-badge">
          <Sparkles size={14} />
          <span>AGENTIC AI FULL-STACK APP BUILDER</span>
        </div>

        {/* Main Headline */}
        <h1 className="emergent-title">
          Build software from idea to production
          <br />
          <span className="emergent-title-gradient">in natural language.</span>
        </h1>

        <p className="emergent-subtitle">
          LocalFoundary plans architecture, writes full-stack React and Python code, configures PostgreSQL schemas, and creates production releases — backed by local SQLite codebase RAG.
        </p>

        {/* Central Large Composer Box */}
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

        {/* Feature Checkmarks Strip */}
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
      </section>

      {/* 2. Platform Capabilities & Architecture Grid */}
      <section className="emergent-section" id="features">
        <div className="emergent-section-header">
          <div className="emergent-section-pill">ENTERPRISE AGENTIC STACK</div>
          <h2 className="emergent-section-title">Everything you need to ship in minutes</h2>
          <p className="emergent-section-desc">
            No toy snippets or incomplete sandboxes. LocalFoundary creates full-stack applications with production architectures and persistent storage.
          </p>
        </div>

        <div className="emergent-features-grid">
          {PLATFORM_FEATURES.map((feat, i) => (
            <div key={i} className="emergent-feature-card">
              <div className="emergent-feature-icon-wrapper">{feat.icon}</div>
              <h3 className="emergent-feature-card-title">{feat.title}</h3>
              <p className="emergent-feature-card-desc">{feat.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 3. Subscription & Credit Pricing Plans */}
      <section className="emergent-section" id="pricing">
        <div className="emergent-section-header">
          <div className="emergent-section-pill">TRANSPARENT CREDIT-BASED PLANS</div>
          <h2 className="emergent-section-title">Scale from prototype to organization</h2>
          <p className="emergent-section-desc">
            Choose the subscription tier that fits your development velocity. All plans include full code exports and GitHub sync.
          </p>

          {/* Billing Switcher */}
          <div className="emergent-pricing-switcher">
            <button
              className={`switcher-btn ${billingPeriod === 'monthly' ? 'active' : ''}`}
              onClick={() => setBillingPeriod('monthly')}>
              Monthly billing
            </button>
            <button
              className={`switcher-btn ${billingPeriod === 'annual' ? 'active' : ''}`}
              onClick={() => setBillingPeriod('annual')}>
              Annual billing
              <span className="annual-save-tag">SAVE 15%</span>
            </button>
          </div>
        </div>

        <div className="emergent-pricing-grid">
          {PRICING_TIERS.map((tier) => {
            const price = billingPeriod === 'annual' ? tier.annualPrice : tier.monthlyPrice;
            return (
              <div
                key={tier.id}
                className={`emergent-pricing-card ${tier.highlight ? 'highlight' : ''}`}>
                {tier.badge && (
                  <div className="pricing-badge">{tier.badge}</div>
                )}
                <div className="pricing-name">{tier.name}</div>
                <div className="pricing-tagline">{tier.tagline}</div>

                <div className="pricing-price-row">
                  <span className="pricing-currency">$</span>
                  <span className="pricing-amount">{price}</span>
                  <span className="pricing-period">/month</span>
                </div>

                <div className="pricing-credits-chip">
                  <Zap size={13} color="#10b981" />
                  <span>{tier.credits}</span>
                </div>

                <button
                  type="button"
                  className={`pricing-cta-btn ${tier.highlight ? 'primary' : 'secondary'}`}
                  onClick={() => {
                    if (!user) {
                      onOpenLogin();
                    } else if (isSuperAdmin && onOpenAdminDashboard) {
                      onOpenAdminDashboard();
                    } else {
                      onStartProject(`Bootstrap app for ${tier.name} tier`, `${tier.name} Workspace`);
                    }
                  }}>
                  {user ? (tier.id === 'free' ? 'Current Plan' : tier.cta) : 'Sign in to Subscribe'}
                </button>

                <div className="pricing-features-list">
                  <div className="pricing-features-title">INCLUDED IN {tier.name.toUpperCase()}:</div>
                  {tier.features.map((f, fi) => (
                    <div key={fi} className="pricing-feature-row">
                      <Check size={14} className="pricing-check-icon" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 4. Frequently Asked Questions */}
      <section className="emergent-section" id="faqs">
        <div className="emergent-section-header">
          <div className="emergent-section-pill">QUESTIONS & ANSWERS</div>
          <h2 className="emergent-section-title">Frequently asked questions</h2>
        </div>

        <div className="emergent-faq-list">
          {FAQS.map((faq, i) => {
            const isOpen = activeFaq === i;
            return (
              <div
                key={i}
                className={`emergent-faq-item ${isOpen ? 'open' : ''}`}
                onClick={() => setActiveFaq(isOpen ? null : i)}>
                <div className="emergent-faq-question">
                  <span>{faq.q}</span>
                  <ChevronDown
                    size={16}
                    style={{ transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}
                  />
                </div>
                {isOpen && (
                  <div className="emergent-faq-answer">
                    <p>{faq.a}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* 5. Pre-Footer Sign-up Call to Action */}
      <section className="emergent-cta-banner">
        <div className="emergent-cta-content">
          <h2 className="emergent-cta-title">Ready to bring your ideas to life?</h2>
          <p className="emergent-cta-desc">
            Sign in with Google, GitHub, or Apple to launch your personal app workspace in seconds.
          </p>
          <div className="emergent-cta-actions">
            <button
              type="button"
              className="emergent-submit-btn"
              onClick={onOpenLogin}>
              <span>{user ? 'Open Workspace' : 'Sign in for free'}</span>
              <ArrowRight size={16} />
            </button>
            <button
              type="button"
              className="action-btn-small"
              onClick={onOpenRecovery}
              style={{ background: '#131e16', color: '#9bb897', border: '1px solid rgba(255,255,255,0.1)', padding: '10px 16px', fontSize: '13px' }}>
              <Upload size={14} /> Import Recovery .enc
            </button>
          </div>
        </div>
      </section>

      {/* 6. Landing Footer */}
      <footer className="emergent-footer">
        <div className="emergent-footer-inner">
          <div className="emergent-footer-left">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f0fdf4', fontWeight: 800 }}>
              <Sparkles size={18} color="#10b981" />
              <span>LocalFoundary</span>
            </div>
            <div style={{ fontSize: '12px', color: '#688265', marginTop: '4px' }}>
              The Agentic Vibe-Coding Platform for Full-Stack Software.
            </div>
          </div>

          <div className="emergent-footer-links">
            <a href="#features">Features</a>
            <a href="#pricing">Subscription Plans</a>
            <a href="#faqs">FAQ</a>
            {isSuperAdmin && onOpenAdminDashboard && (
              <button
                type="button"
                onClick={onOpenAdminDashboard}
                style={{ background: 'none', border: 'none', color: '#34d399', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}>
                Super Admin Dashboard
              </button>
            )}
          </div>
        </div>
        <div className="emergent-footer-bottom">
          <span>© 2026 LocalFoundary. All rights reserved.</span>
          <span>100% Code Ownership • Local SQLite RAG • PostgreSQL</span>
        </div>
      </footer>
    </div>
  );
}
