const memory = new Map();
globalThis.location = {hash:'',pathname:'/'};
globalThis.history = {replaceState(){}};
globalThis.sessionStorage = globalThis.localStorage = {getItem:key=>memory.get(key)||null,setItem:(key,value)=>memory.set(key,value),removeItem:key=>memory.delete(key)};
