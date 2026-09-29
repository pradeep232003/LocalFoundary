import {useEffect, useState} from 'react';

export default function App() {
  const [notes, setNotes] = useState([]);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function load() {
    try {
      const r = await fetch('/api/notes');
      if (!r.ok) throw new Error('Could not load notes. Check the backend logs.');
      setNotes(await r.json());
    } catch (e) {setError(e.message);}
  }
  useEffect(() => {load();}, []);
  async function add(e) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const r = await fetch('/api/notes', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text})});
      if (!r.ok) throw new Error('Could not save the note.');
      setText(''); await load();
    } catch (e) {setError(e.message);} finally {setBusy(false);}
  }
  return <main><div className="eyebrow">YOUR LOCAL WORKSPACE</div><h1>A small idea.<br/><span>A working app.</span></h1>
    <p className="intro">React, Python, and a real PostgreSQL database. Ready for your next idea.</p>
    <section><h2>Project notebook <small>{notes.length} notes</small></h2>
      <form onSubmit={add}><input aria-label="New note" value={text} maxLength={1000} onChange={e => setText(e.target.value)} placeholder="Write your first idea…"/><button disabled={busy || !text.trim()}>{busy ? 'Saving…' : 'Add note'}</button></form>
      {error && <p role="alert">{error}</p>}
      {!notes.length && <p className="empty">Your notes will appear here. They stay saved when you stop the preview.</p>}
      {notes.map(n => <article key={n.id}><span className="dot"/>{n.text}</article>)}
    </section><footer>Built on your laptop · Your project, your code</footer></main>;
}
