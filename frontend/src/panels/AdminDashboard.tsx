import React from 'react';
import { useAuth } from '../AuthContext';
export default function AdminDashboard({ onClose, onOpenProject, projects = [] }: {
  onClose: () => void; onOpenProject: (id: string) => void;
  projects: { id: string; name: string; repo?: string; created_at?: string }[];
}) {
  const { user } = useAuth();
  if (!user) return <p role="alert">Unlock the workspace to view projects.</p>;
  return <section style={{ padding: 32 }}><button onClick={onClose}>Return to builder</button>
    <h1>Workspace overview</h1><p>{projects.length} saved projects in your personal workspace.</p>
    <p>Application users, roles and billing belong to each generated Accounts starter. This builder does not provide a shared, multi-tenant administration service.</p>
    {projects.length ? <ul>{projects.map(p => <li key={p.id}><button onClick={() => onOpenProject(p.id)}>{p.name}</button>{p.repo && <span> · GitHub: {p.repo}</span>}</li>)}</ul> : <p>Create a project to get started.</p>}
  </section>;
}
