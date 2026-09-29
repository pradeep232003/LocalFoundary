import test from 'node:test';
import assert from 'node:assert/strict';
const storage = new Map();
globalThis.location = { hash: '#token=launch-secret', pathname: '/' };
globalThis.sessionStorage = { getItem: key => storage.get(key), setItem: (key,value) => storage.set(key,value) };
globalThis.history = { replaceState: (_,__,path) => { globalThis.location.hash = ''; assert.equal(path,'/'); } };
const {request, importRecovery} = await import('../src/api.js');
test('launch token is removed from URL and forwarded for JSON and binary API operations', async () => {
  assert.equal(location.hash,'');
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push({url,...options}); return new Response('{"ok":true}',{headers:{'Content-Type':'application/json'}}); };
  await request('/projects',{name:'Example'});
  await importRecovery(new Blob(['archive']),'test password');
  assert.equal(calls.length,2);
  assert.equal(calls[0].headers.Authorization,'Bearer launch-secret');
  assert.equal(calls[1].headers.Authorization,'Bearer launch-secret');
  assert.equal(calls[1].headers['Content-Type'],'application/octet-stream');
});
test('failed authentication never returns a successful response or download', async () => {
  globalThis.fetch = async () => new Response('{"detail":"Unlock workspace"}',{status:401});
  await assert.rejects(request('/projects'),/Unlock workspace/);
  await assert.rejects(request('/projects/id/rag/export-db',undefined,{blob:true}),/Unlock workspace/);
});
