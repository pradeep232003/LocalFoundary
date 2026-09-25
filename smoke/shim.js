// Minimal browser globals so module-level code can be imported under Node.
const store = new Map();
globalThis.sessionStorage = {
  getItem: key => (store.has(key) ? store.get(key) : null),
  setItem: (key, value) => store.set(key, String(value)),
  removeItem: key => store.delete(key),
};
globalThis.localStorage = globalThis.sessionStorage;
globalThis.location = { href: 'http://127.0.0.1:8765/', hash: '#token=smoke-token', origin: 'http://127.0.0.1:8765' };
globalThis.history = { replaceState: () => {} };
globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({}), text: async () => '' });
