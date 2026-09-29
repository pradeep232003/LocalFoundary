import { useEffect, useState } from 'react';
import { request, downloadBlob } from '../api';
export default function CodebaseRagPanel({ project, id, running, onSelectPrompt }) {
 const [status,setStatus]=useState(null),[query,setQuery]=useState(''),[result,setResult]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let active=true; setStatus(null);setResult(null);request(`/projects/${id}/rag/status`).then(v=>{if(active)setStatus(v);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[id]);
 async function action(fn){setBusy(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <section style={{padding:24}}><h2>Source search and context</h2><p>Local SQLite FTS5 keyword search. Matching source excerpts can be included in coding requests. Token counts are text-length estimates, not measured provider savings.</p>
 {status && <p>{status.indexed_files} indexed files · {status.queries} searches · {status.enabled?'Context enabled':'Context disabled'}</p>}
 <button disabled={busy||running} onClick={()=>action(async()=>setStatus(await request(`/projects/${id}/rag/reindex`,{})))}>Reindex</button>
 <button disabled={busy||!status} onClick={()=>action(async()=>{await request(`/projects/${id}/rag/config`,{enabled:!status.enabled});setStatus(await request(`/projects/${id}/rag/status`));})}>Toggle coding context</button>
 <button disabled={busy} onClick={()=>action(()=>downloadBlob(`/projects/${id}/rag/export-db`,'codebase.sqlite'))}>Download SQLite database</button>
 <form onSubmit={e=>{e.preventDefault();action(async()=>setResult(await request(`/projects/${id}/rag/search`,{query,top_k:3})));}}><label>Search source<input required minLength={2} value={query} onChange={e=>setQuery(e.target.value)}/></label><button disabled={busy}>Search</button></form>
 {result && <><p>{result.matched_files.length} matches. Approximate excerpt tokens: {result.tokens_rag_injected}.</p>{result.matched_files.map(file=><details key={file.file_path}><summary>{file.file_path}{file.truncated?' (excerpt)':''}</summary><pre style={{whiteSpace:'pre-wrap'}}>{file.content}</pre></details>)}<button onClick={()=>onSelectPrompt?.(query)}>Use query in composer</button></>}
 {error&&<p role="alert">{error}</p>}</section>;
}
