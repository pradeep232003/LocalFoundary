import React, { useState, useEffect, useRef } from 'react';
import {
  Search,
  Database,
  Code2,
  Monitor,
  Wand2,
  BookOpen,
  Settings,
  Camera,
  Package,
  Rocket,
  Smartphone,
  Terminal,
  History,
  Files,
  Archive,
  RefreshCw,
  Download,
  Zap,
  CheckCircle2,
  FileCode2,
  Sparkles,
  ArrowRight,
  SlidersHorizontal,
  Shield,
} from 'lucide-react';
import './command-palette.css';

export default function CommandPalette({
  isOpen,
  onClose,
  currentTab,
  onSelectTab,
  onSelectPrompt,
  onTriggerAction,
  project,
}) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);

  // Tab navigation items
  const tabItems = [
    { id: 'tab-preview', category: 'Navigation', icon: Monitor, label: 'Preview Application', sub: 'Interactive live preview frame', action: () => onSelectTab('preview') },
    { id: 'tab-rag', category: 'Navigation', icon: Database, label: 'Vector RAG Studio', sub: 'Inspect SQLite embeddings & token pruning', badge: 'Active', action: () => onSelectTab('rag') },
    { id: 'tab-code', category: 'Navigation', icon: Code2, label: 'Code Editor', sub: 'Browse and edit project source files', action: () => onSelectTab('code') },
    { id: 'tab-files', category: 'Navigation', icon: Files, label: 'Managed Files', sub: 'Asset files and container volumes', action: () => onSelectTab('files') },
    { id: 'tab-documents', category: 'Navigation', icon: BookOpen, label: 'Documents & RAG Data', sub: 'Project knowledgebase and specs', action: () => onSelectTab('documents') },
    { id: 'tab-roadmap', category: 'Navigation', icon: Wand2, label: 'Roadmap & Specs', sub: 'Product milestones and user stories', action: () => onSelectTab('roadmap') },
    { id: 'tab-settings', category: 'Navigation', icon: Settings, label: 'App Settings', sub: 'Environment vars, ports, build config', action: () => onSelectTab('settings') },
    { id: 'tab-packages', category: 'Navigation', icon: Package, label: 'Packages & Deps', sub: 'NPM and Python dependencies', action: () => onSelectTab('packages') },
    { id: 'tab-release', category: 'Navigation', icon: Rocket, label: 'Release & Deploy', sub: 'GitHub push and build releases', action: () => onSelectTab('release') },
    { id: 'tab-mobile', category: 'Navigation', icon: Smartphone, label: 'Mobile Emulators', sub: 'Test responsive viewports', action: () => onSelectTab('mobile') },
    { id: 'tab-logs', category: 'Navigation', icon: Terminal, label: 'Live Logs', sub: 'Container stdout and build events', action: () => onSelectTab('logs') },
    { id: 'tab-versions', category: 'Navigation', icon: History, label: 'Version Timeline', sub: 'Revert to previous checkpoints', action: () => onSelectTab('versions') },
    { id: 'tab-recovery', category: 'Navigation', icon: Archive, label: 'Recovery & Backups', sub: 'Project snapshots and integrity checks', action: () => onSelectTab('recovery') },
  ];

  // Quick Action items
  const actionItems = [
    {
      id: 'act-super-admin',
      category: 'Actions',
      icon: Shield,
      label: 'Super Admin Dashboard',
      sub: 'Manage subscriber organizations, billing plans, and system quotas',
      badge: 'Admin',
      action: () => onTriggerAction('open-admin'),
    },
    {
      id: 'act-reindex',
      category: 'Actions',
      icon: RefreshCw,
      label: 'Reindex Codebase Vector Store',
      sub: 'Recalculate 768-dim embeddings in SQLite with nomic-embed-text',
      badge: 'RAG',
      action: () => onTriggerAction('reindex-rag'),
    },
    {
      id: 'act-export-sqlite',
      category: 'Actions',
      icon: Download,
      label: 'Export SQLite Vector Database',
      sub: 'Download codebase_rag.db binary file for local inspection',
      badge: 'SQLite',
      action: () => onTriggerAction('export-sqlite'),
    },
    {
      id: 'act-toggle-rag',
      category: 'Actions',
      icon: Zap,
      label: 'Toggle RAG Prompt Pruning',
      sub: 'Switch between smart context injection and full-codebase paste',
      action: () => onTriggerAction('toggle-rag'),
    },
    {
      id: 'act-global-settings',
      category: 'Actions',
      icon: SlidersHorizontal,
      label: 'Open Global Settings',
      sub: 'Configure AI providers, rate limits, and SQLite storage',
      action: () => onTriggerAction('open-settings'),
    },
    {
      id: 'act-download-zip',
      category: 'Actions',
      icon: Download,
      label: 'Download Project Archive (ZIP)',
      sub: 'Export complete repository files and config',
      action: () => onTriggerAction('download-zip'),
    },
  ];

  // Quick Prompts
  const promptItems = [
    {
      id: 'p-1',
      category: 'Quick Prompts',
      icon: Sparkles,
      label: 'Update habit streak calculation and card progress display',
      sub: 'Injects App.jsx & style.css (-71% tokens)',
      action: () => onSelectPrompt('Update habit streak calculation and card progress display'),
    },
    {
      id: 'p-2',
      category: 'Quick Prompts',
      icon: Sparkles,
      label: 'Add FastAPI endpoint for habit check-in with streak increment',
      sub: 'Injects main.py and data models',
      action: () => onSelectPrompt('Add FastAPI endpoint for habit check-in with streak increment'),
    },
    {
      id: 'p-3',
      category: 'Quick Prompts',
      icon: Sparkles,
      label: 'PostgreSQL habits table schema and database migrations',
      sub: 'Injects 001_initial.sql and schema files',
      action: () => onSelectPrompt('PostgreSQL habits table schema and database migrations'),
    },
    {
      id: 'p-4',
      category: 'Quick Prompts',
      icon: Sparkles,
      label: 'Dark mode styling, CSS grid layout, and streak badge colors',
      sub: 'Injects style.css and layout components',
      action: () => onSelectPrompt('Dark mode styling, CSS grid layout, and streak badge colors'),
    },
  ];

  const allItems = [...actionItems, ...tabItems, ...promptItems];

  const filteredItems = query.trim()
    ? allItems.filter(
        item =>
          item.label.toLowerCase().includes(query.toLowerCase()) ||
          item.sub.toLowerCase().includes(query.toLowerCase()) ||
          item.category.toLowerCase().includes(query.toLowerCase())
      )
    : allItems;

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => (prev + 1) % (filteredItems.length || 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => (prev - 1 + filteredItems.length) % (filteredItems.length || 1));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filteredItems[selectedIndex]) {
          filteredItems[selectedIndex].action();
          onClose();
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, filteredItems, selectedIndex, onClose]);

  if (!isOpen) return null;

  return (
    <div className="cmd-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="cmd-modal" onClick={e => e.stopPropagation()}>
        {/* Search Input Bar */}
        <div className="cmd-input-wrap">
          <Search size={18} className="cmd-search-icon" />
          <input
            ref={inputRef}
            type="text"
            className="cmd-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Type a command, navigate tab, or trigger RAG action… (Esc to exit)"
          />
          <kbd className="cmd-kbd">ESC</kbd>
        </div>

        {/* Results List */}
        <div className="cmd-results">
          {filteredItems.length === 0 ? (
            <div className="cmd-empty">
              No matching commands or actions found for "{query}".
            </div>
          ) : (
            filteredItems.map((item, idx) => {
              const Icon = item.icon;
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={item.id}
                  className={`cmd-item ${isSelected ? 'selected' : ''}`}
                  onClick={() => {
                    item.action();
                    onClose();
                  }}
                  onMouseEnter={() => setSelectedIndex(idx)}>
                  <div className="cmd-item-icon">
                    <Icon size={16} />
                  </div>
                  <div className="cmd-item-content">
                    <div className="cmd-item-title-row">
                      <span className="cmd-item-title">{item.label}</span>
                      {item.badge && <span className="cmd-item-badge">{item.badge}</span>}
                      <span className="cmd-item-cat">{item.category}</span>
                    </div>
                    <div className="cmd-item-sub">{item.sub}</div>
                  </div>
                  <ArrowRight size={14} className="cmd-item-arrow" />
                </div>
              );
            })
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="cmd-footer">
          <div className="cmd-shortcuts">
            <span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span>
            <span><kbd>↵</kbd> Execute</span>
            <span><kbd>ESC</kbd> Close</span>
          </div>
          <div className="cmd-footer-tag">
            <Database size={11} color="#10b981" />
            <span>Local Foundry RAG Studio</span>
          </div>
        </div>
      </div>
    </div>
  );
}
