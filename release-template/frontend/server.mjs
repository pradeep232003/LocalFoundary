// Trusted static server + fixed upstream proxy. No dev server and no arbitrary targets.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
const root = '/srv/app';
const types = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css',
  '.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg',
  '.gif':'image/gif','.ico':'image/x-icon','.woff':'font/woff','.woff2':'font/woff2','.txt':'text/plain'};
const hopHeaders = new Set(['connection','keep-alive','proxy-authenticate','proxy-authorization','te','trailer','transfer-encoding','upgrade']);
const filter = headers => Object.fromEntries(Object.entries(headers).filter(([key]) => !hopHeaders.has(key.toLowerCase())));
const server = http.createServer((req, res) => {
  const requestId = randomUUID();
  res.setHeader('X-Request-ID', requestId);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'");
  if (req.url === '/healthz') { res.end('ok'); return; }
  if (req.url === '/api' || req.url.startsWith('/api/')) {
    if (!['GET','POST','PATCH','PUT','DELETE','HEAD','OPTIONS'].includes(req.method)) { res.writeHead(405); res.end(); return; }
    if (Number(req.headers['content-length'] || 0) > 65536) {res.writeHead(413); res.end('Request too large'); return;}
    const headers = filter(req.headers);
    for (const key of Object.keys(headers)) if (key.startsWith('x-forwarded-') || ['forwarded','x-real-ip','x-request-id'].includes(key)) delete headers[key];
    headers['x-request-id'] = requestId;
    // Buffer at most 64 KiB; never forward a partial oversized body.
    const chunks = []; let size = 0;
    req.on('data', chunk => {size += chunk.length; if (size > 65536) {if (!res.headersSent) res.writeHead(413); res.end('Request too large');} else chunks.push(chunk);});
    req.on('end', () => {
    if (size > 65536) return;
    const upstream = http.request({hostname:'api',port:8000,path:req.url,method:req.method,
      headers:{...headers, 'content-length': String(size)}, timeout:30000}, response => {
      res.writeHead(response.statusCode, filter(response.headers)); response.pipe(res);
    });
    upstream.on('timeout', () => upstream.destroy());
    upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end('Backend unavailable'); });
    req.on('aborted', () => upstream.destroy()); upstream.end(Buffer.concat(chunks));
    }); return;
  }
  if (/^\/(ops|metrics|docs|openapi\.json)(\/|\?|$)/.test(req.url)) {res.writeHead(404); res.end(); return;}
  if (!['GET','HEAD'].includes(req.method)) { res.writeHead(405); res.end(); return; }
  let requested;
  try { requested = decodeURIComponent(new URL(req.url,'http://local').pathname); }
  catch { res.writeHead(400); res.end(); return; }
  let target = path.resolve(root, '.' + requested);
  if (!target.startsWith(root + '/') && target !== root) { res.writeHead(403); res.end(); return; }
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
    if (path.extname(requested)) { res.writeHead(404); res.end(); return; }
    target = path.join(root, 'index.html');
  }
  res.setHeader('Content-Type', types[path.extname(target)] || 'application/octet-stream');
  res.setHeader('Cache-Control', path.basename(target) === 'index.html' ? 'no-store' : 'public, max-age=3600');
  if (req.method === 'HEAD') { res.end(); return; }
  const stream = fs.createReadStream(target);
  stream.on('error', () => { if (!res.headersSent) res.writeHead(500); res.end(); }); stream.pipe(res);
});
server.requestTimeout = 30000;
server.headersTimeout = 15000;
server.maxHeadersCount = 60;
server.maxRequestsPerSocket = 200;
server.listen(8080, '0.0.0.0');
