import React, { useState } from 'react';
import { Code2, Database, Bot, GitBranch, Lock, Smartphone } from 'lucide-react';
import './emergent-hero.css';
export default function EmergentLanding({onStartProject,onOpenRecovery,onOpenLogin,user,onOpenAdminDashboard,onOpenAgentBuilder,projects=[],onSelectProject}: any) {
 const [prompt,setPrompt]=useState('');
 const capabilities=[
  [Code2,'Build with your model','React, Python and PostgreSQL projects with source editing, validation and repair attempts.'],
  [Lock,'Personal and local','A token-protected workspace. Offline mode uses a prepared model on this computer.'],
  [Database,'Persistent project history','Source snapshots, chat, project context and PostgreSQL metadata survive restarts.'],
  [Bot,'Coding, documents and files','Run real model tools. Review file plans before applying changes.'],
  [GitBranch,'GitHub and recovery','Review changes before saving to GitHub. Export encrypted recovery archives.'],
  [Smartphone,'Mobile build tools','Build APK/AAB with Android tools or IPA on macOS with Xcode and signing.'],
 ];
 return <div className="emergent-hero-container">
  <nav aria-label="Workspace navigation" style={{display:'flex',gap:12,justifyContent:'space-between',width:'100%',flexWrap:'wrap'}}><strong>Local Foundry</strong><div><button onClick={()=>onOpenLogin()}> {user?'Workspace session':'Unlock workspace'}</button> <button onClick={onOpenAdminDashboard}>Projects</button> <button onClick={onOpenAgentBuilder}>Agent Studio</button></div></nav>
  <div className="emergent-pill-badge">YOUR PERSONAL APP STUDIO</div>
  <h1 className="emergent-title">Build your next application<br/><span className="emergent-title-gradient">one conversation at a time.</span></h1>
  <p className="emergent-subtitle">Describe an idea, inspect the code, and preview it in a Docker sandbox. Use Claude, OpenAI, or a local model.</p>
  <form className="emergent-composer-card" onSubmit={e=>{e.preventDefault();if(!user){onOpenLogin();return;}onStartProject(prompt,prompt.split(/\s+/).slice(0,4).join(' ').slice(0,60)||'New app');}}>
    <label htmlFor="new-app-prompt">What would you like to build?</label><textarea id="new-app-prompt" className="emergent-textarea" required rows={4} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="A client portal with project tracking and a PostgreSQL database…"/>
    <div className="emergent-composer-bottom"><span>React · FastAPI · PostgreSQL</span><button className="primary" disabled={!prompt.trim()}>Create project</button></div>
  </form>
  <p>Cloud model usage is billed by your provider. Native packaging and uncached dependencies need a connection.</p>
  <div style={{display:'flex',gap:12}}><button onClick={()=>onStartProject('','New application')}>Start from a template</button><button onClick={onOpenRecovery}>Import recovery archive</button></div>
  <section aria-label="Saved projects" style={{width:'100%',margin:'28px 0'}}><h2>Your projects</h2>{projects.length?<div style={{display:'flex',gap:12,flexWrap:'wrap'}}>{projects.map((p:any)=><button key={p.id} onClick={()=>onSelectProject(p.id)}>{p.name}</button>)}</div>:<p>{user?'No projects yet. Create one above.':'Unlock your workspace to load saved projects.'}</p>}</section>
  <section aria-label="Capabilities" style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(240px,1fr))',gap:18,width:'100%'}}>{capabilities.map(([Icon,title,text]:any)=><article key={title} style={{border:'1px solid #2c4233',borderRadius:12,padding:22,textAlign:'left'}}><Icon size={22}/><h2 style={{fontSize:18}}>{title}</h2><p>{text}</p></article>)}</section>
 </div>;
}
