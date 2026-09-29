export default {
  cacheDir: '/tmp/vite-cache',
  esbuild: {jsx: 'automatic'},
  server: {
    host: '0.0.0.0', port: 5173, strictPort: true,
    allowedHosts: ['127.0.0.1', 'localhost', 'web'],
    proxy: {'/api': {target: 'http://api:8000', changeOrigin: true}},
    headers: {
      'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self' ws://127.0.0.1:* ws://web:5173; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors http://127.0.0.1:8765 http://localhost:8765",
      'Referrer-Policy': 'no-referrer'
    },
    watch: {usePolling: true, interval: 500}
  }
};
