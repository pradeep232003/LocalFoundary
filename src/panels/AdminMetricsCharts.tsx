import React, { useState } from 'react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import {
  TrendingUp,
  BarChart3,
  Activity,
  Layers,
  Sparkles,
  Calendar,
  Cpu,
  Zap,
  ArrowUpRight,
  Database,
  PieChart as PieIcon,
} from 'lucide-react';

// Monthly subscription and MRR trend
const SUBSCRIPTION_TRENDS = [
  { month: 'Apr', starter: 8, pro: 12, enterprise: 3, totalUsers: 23, mrr: 2077, appGenerations: 142 },
  { month: 'May', starter: 14, pro: 19, enterprise: 5, totalUsers: 38, mrr: 3402, appGenerations: 268 },
  { month: 'Jun', starter: 22, pro: 28, enterprise: 7, totalUsers: 57, mrr: 4943, appGenerations: 430 },
  { month: 'Jul', starter: 35, pro: 44, enterprise: 11, totalUsers: 90, mrr: 7779, appGenerations: 720 },
  { month: 'Aug', starter: 48, pro: 65, enterprise: 16, totalUsers: 129, mrr: 11311, appGenerations: 1150 },
  { month: 'Sep', starter: 64, pro: 92, enterprise: 23, totalUsers: 179, mrr: 15998, appGenerations: 1640 },
];

// Daily system-wide app generation frequency (last 14 days)
const APP_GENERATION_FREQUENCY = [
  { day: 'Sep 13', fullStackApps: 42, mobileApks: 8, ragEmbeddings: 180, tokenSavingsPct: 68 },
  { day: 'Sep 14', fullStackApps: 55, mobileApks: 12, ragEmbeddings: 240, tokenSavingsPct: 70 },
  { day: 'Sep 15', fullStackApps: 61, mobileApks: 15, ragEmbeddings: 290, tokenSavingsPct: 72 },
  { day: 'Sep 16', fullStackApps: 78, mobileApks: 22, ragEmbeddings: 380, tokenSavingsPct: 71 },
  { day: 'Sep 17', fullStackApps: 84, mobileApks: 19, ragEmbeddings: 410, tokenSavingsPct: 69 },
  { day: 'Sep 18', fullStackApps: 92, mobileApks: 28, ragEmbeddings: 490, tokenSavingsPct: 73 },
  { day: 'Sep 19', fullStackApps: 88, mobileApks: 24, ragEmbeddings: 460, tokenSavingsPct: 71 },
  { day: 'Sep 20', fullStackApps: 96, mobileApks: 31, ragEmbeddings: 520, tokenSavingsPct: 74 },
  { day: 'Sep 21', fullStackApps: 110, mobileApks: 35, ragEmbeddings: 590, tokenSavingsPct: 72 },
  { day: 'Sep 22', fullStackApps: 104, mobileApks: 29, ragEmbeddings: 560, tokenSavingsPct: 70 },
  { day: 'Sep 23', fullStackApps: 122, mobileApks: 38, ragEmbeddings: 680, tokenSavingsPct: 73 },
  { day: 'Sep 24', fullStackApps: 135, mobileApks: 44, ragEmbeddings: 740, tokenSavingsPct: 75 },
  { day: 'Sep 25', fullStackApps: 148, mobileApks: 49, ragEmbeddings: 810, tokenSavingsPct: 71 },
  { day: 'Sep 26', fullStackApps: 162, mobileApks: 54, ragEmbeddings: 890, tokenSavingsPct: 74 },
];

// Tier distribution for pie chart
const TIER_DISTRIBUTION = [
  { name: 'Starter ($29/mo)', value: 64, color: '#38bdf8' },
  { name: 'Pro ($79/mo)', value: 92, color: '#10b981' },
  { name: 'Enterprise ($299/mo)', value: 23, color: '#f59e0b' },
];

// Hourly peak generation load
const HOURLY_GENERATION_HEAT = [
  { hour: '00:00', builds: 18 },
  { hour: '03:00', builds: 9 },
  { hour: '06:00', builds: 14 },
  { hour: '09:00', builds: 68 },
  { hour: '12:00', builds: 112 },
  { hour: '15:00', builds: 146 },
  { hour: '18:00', builds: 128 },
  { hour: '21:00', builds: 82 },
];

export default function AdminMetricsCharts() {
  const [timeRange, setTimeRange] = useState<'6m' | '14d' | '24h'>('14d');
  const [metricView, setMetricView] = useState<'generations' | 'revenue' | 'tokens'>('generations');

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div style={{
          background: '#0d1510',
          border: '1px solid rgba(16, 185, 129, 0.4)',
          padding: '10px 14px',
          borderRadius: '8px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
          fontSize: '12px',
          color: '#f0fdf4',
        }}>
          <div style={{ fontWeight: 700, marginBottom: '6px', color: '#34d399' }}>{label}</div>
          {payload.map((entry: any, index: number) => (
            <div key={`item-${index}`} style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '3px 0' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: entry.color || entry.fill }} />
              <span style={{ color: '#9bb197' }}>{entry.name}:</span>
              <span style={{ fontWeight: 700, color: '#ffffff' }}>
                {entry.name.includes('$') || entry.name.toLowerCase().includes('mrr') ? `$${entry.value.toLocaleString()}` : entry.value.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Visual Analytics Header & Range Controls */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '12px',
        background: '#111a14',
        padding: '14px 18px',
        borderRadius: '10px',
        border: '1px solid rgba(255, 255, 255, 0.08)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            background: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            padding: '6px',
            borderRadius: '6px',
            color: '#10b981',
          }}>
            <BarChart3 size={18} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '15px', color: '#f0fdf4' }}>
              Platform Intelligence & Recharts Visualizer
            </div>
            <div style={{ fontSize: '11px', color: '#8fa387' }}>
              Real-time monitoring of tenant subscriber cohorts, app generation velocity, and token efficiency
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ display: 'flex', background: '#0a110d', padding: '3px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.06)' }}>
            <button
              onClick={() => setMetricView('generations')}
              style={{
                background: metricView === 'generations' ? '#10b981' : 'transparent',
                color: metricView === 'generations' ? '#041d0f' : '#8fa387',
                border: 'none',
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
              }}>
              App Velocity
            </button>
            <button
              onClick={() => setMetricView('revenue')}
              style={{
                background: metricView === 'revenue' ? '#10b981' : 'transparent',
                color: metricView === 'revenue' ? '#041d0f' : '#8fa387',
                border: 'none',
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
              }}>
              Subscriber MRR
            </button>
            <button
              onClick={() => setMetricView('tokens')}
              style={{
                background: metricView === 'tokens' ? '#10b981' : 'transparent',
                color: metricView === 'tokens' ? '#041d0f' : '#8fa387',
                border: 'none',
                padding: '4px 10px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
              }}>
              RAG Embeddings
            </button>
          </div>
        </div>
      </div>

      {/* Row 1: Primary Large Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        {/* Main Chart 1: System-wide App Generation Frequency or MRR */}
        <div style={{
          background: '#111a14',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '10px',
          padding: '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <TrendingUp size={16} color="#10b981" />
              <span style={{ fontWeight: 700, fontSize: '14px', color: '#f0fdf4' }}>
                {metricView === 'generations'
                  ? 'System-Wide App Generation Frequency (Last 14 Days)'
                  : metricView === 'revenue'
                  ? 'Monthly Recurring Revenue (MRR Growth $USD)'
                  : 'Daily SQLite Vector Embeddings & Prompt Pruning'}
              </span>
            </div>
            <span style={{ fontSize: '11px', color: '#34d399', background: '#0a160f', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(16,185,129,0.3)' }}>
              ⚡ +28% MoM Acceleration
            </span>
          </div>

          <div style={{ width: '100%', height: '260px' }}>
            <ResponsiveContainer width="100%" height="100%">
              {metricView === 'generations' ? (
                <AreaChart data={APP_GENERATION_FREQUENCY} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorApps" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.6} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                    </linearGradient>
                    <linearGradient id="colorApks" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.5} />
                      <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="day" stroke="#688264" fontSize={11} tickLine={false} />
                  <YAxis stroke="#688264" fontSize={11} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="fullStackApps" name="Full-Stack Apps" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#colorApps)" />
                  <Area type="monotone" dataKey="mobileApks" name="Mobile APK Builds" stroke="#38bdf8" strokeWidth={2} fillOpacity={1} fill="url(#colorApks)" />
                </AreaChart>
              ) : metricView === 'revenue' ? (
                <AreaChart data={SUBSCRIPTION_TRENDS} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorMrr" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#34d399" stopOpacity={0.7} />
                      <stop offset="95%" stopColor="#34d399" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="month" stroke="#688264" fontSize={11} tickLine={false} />
                  <YAxis stroke="#688264" fontSize={11} tickLine={false} tickFormatter={(val) => `$${val / 1000}k`} />
                  <Tooltip content={<CustomTooltip />} />
                  <Area type="monotone" dataKey="mrr" name="MRR ($USD)" stroke="#34d399" strokeWidth={3} fillOpacity={1} fill="url(#colorMrr)" />
                </AreaChart>
              ) : (
                <BarChart data={APP_GENERATION_FREQUENCY} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="day" stroke="#688264" fontSize={11} tickLine={false} />
                  <YAxis stroke="#688264" fontSize={11} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="ragEmbeddings" name="SQLite Embeddings (768-dim)" fill="#a855f7" radius={[4, 4, 0, 0]} />
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: '11px', color: '#8fa387' }}>
            <span>Telemetry: Live PostgreSQL & SQLite event bus</span>
            <span style={{ color: '#34d399', fontWeight: 600 }}>Avg 162 apps / day generated platform-wide</span>
          </div>
        </div>

        {/* Secondary Chart: Subscriber Cohort Breakdown Pie */}
        <div style={{
          background: '#111a14',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '10px',
          padding: '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <PieIcon size={16} color="#38bdf8" />
            <span style={{ fontWeight: 700, fontSize: '14px', color: '#f0fdf4' }}>
              Active Subscription Distribution
            </span>
          </div>

          <div style={{ width: '100%', height: '180px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={TIER_DISTRIBUTION}
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={75}
                  paddingAngle={4}
                  dataKey="value">
                  {TIER_DISTRIBUTION.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Custom legend */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '11px' }}>
            {TIER_DISTRIBUTION.map((tier) => (
              <div key={tier.name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: tier.color }} />
                  <span style={{ color: '#c4d7c2' }}>{tier.name}</span>
                </div>
                <span style={{ fontWeight: 700, color: '#f0fdf4' }}>{tier.value} accounts</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Row 2: Secondary Bar Chart - Subscription Growth by Cohort (Stacked) */}
      <div style={{
        background: '#111a14',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '10px',
        padding: '18px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={16} color="#c084fc" />
            <span style={{ fontWeight: 700, fontSize: '14px', color: '#f0fdf4' }}>
              Monthly Subscription Tier Cohort Expansion (Starter vs Pro vs Enterprise)
            </span>
          </div>
          <div style={{ display: 'flex', gap: '16px', fontSize: '11px', color: '#8fa387' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#38bdf8' }} /> Starter
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#10b981' }} /> Pro ($79)
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '2px', background: '#f59e0b' }} /> Enterprise ($299)
            </span>
          </div>
        </div>

        <div style={{ width: '100%', height: '220px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={SUBSCRIPTION_TRENDS} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="month" stroke="#688264" fontSize={11} tickLine={false} />
              <YAxis stroke="#688264" fontSize={11} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="starter" name="Starter ($29/mo)" stackId="a" fill="#38bdf8" />
              <Bar dataKey="pro" name="Pro ($79/mo)" stackId="a" fill="#10b981" />
              <Bar dataKey="enterprise" name="Enterprise ($299/mo)" stackId="a" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
