#!/usr/bin/env node
/** Capture store screenshots of a deployed app at exact submission dimensions.
 *
 * Driven by scripts/mobile.py, which validates the configuration, strips the alpha
 * channel afterwards and checks the results. Run it through that command rather than
 * directly, so a capture cannot reach a store without those checks.
 *
 * Talks to Chrome over DevTools, so no npm browser package is needed. Actions before
 * a capture are limited to fill, click and wait: there is no arbitrary evaluation,
 * because the configuration may come from somewhere less trusted than this script.
 */
import { spawn, spawnSync } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';

// CSS viewport × device pixel ratio must equal the store's required pixel size
// exactly; anything else is rejected or silently rescaled at upload.
export const DEVICES = {
  'iphone-6.9': { label: 'iPhone 6.9"', width: 420, height: 912, scale: 3, pixels: [1260, 2736], store: 'apple' },
  'iphone-6.5': { label: 'iPhone 6.5"', width: 428, height: 926, scale: 3, pixels: [1284, 2778], store: 'apple' },
  'ipad-13': { label: 'iPad 13"', width: 1032, height: 1376, scale: 2, pixels: [2064, 2752], store: 'apple' },
  'android-phone': { label: 'Android phone', width: 360, height: 640, scale: 3, pixels: [1080, 1920], store: 'play' },
  'android-tablet-10': { label: 'Android 10" tablet', width: 800, height: 1280, scale: 2, pixels: [1600, 2560], store: 'play' },
};

function chromePath() {
  const candidates = [process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium'];
  for (const path of candidates) if (path && existsSync(path)) return path;
  for (const name of ['google-chrome', 'chromium', 'chromium-browser']) {
    const result = spawnSync('which', [name], { encoding: 'utf8' });
    if (result.status === 0 && result.stdout.trim()) return result.stdout.trim();
  }
  throw new Error('Chrome or Chromium was not found. Install one, or set CHROME_PATH.');
}

function cdp(websocketUrl) {
  return new Promise((resolveConnection, rejectConnection) => {
    const socket = new WebSocket(websocketUrl);
    const pending = new Map();
    let nextId = 1;
    socket.addEventListener('open', () => resolveConnection({
      send(method, params = {}, sessionId) {
        const id = nextId++;
        return new Promise((resolveCall, rejectCall) => {
          const timer = setTimeout(() => { pending.delete(id); rejectCall(new Error(`CDP timeout: ${method}`)); }, 30000);
          pending.set(id, { resolveCall, rejectCall, timer });
          socket.send(JSON.stringify({ id, method, params, sessionId }));
        });
      },
      close() { socket.close(); },
    }));
    socket.addEventListener('error', () => rejectConnection(new Error('Could not connect to Chrome DevTools.')));
    socket.addEventListener('message', event => {
      const message = JSON.parse(String(event.data));
      if (!message.id || !pending.has(message.id)) return;
      const call = pending.get(message.id);
      clearTimeout(call.timer);
      pending.delete(message.id);
      if (message.error) call.rejectCall(new Error(message.error.message));
      else call.resolveCall(message.result);
    });
  });
}

async function evaluate(client, expression) {
  const result = await client.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text || 'evaluation failed');
  }
  return result.result.value;
}

const quoted = value => JSON.stringify(String(value));

async function waitForSelector(client, selector, timeout = 15000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await evaluate(client, `Boolean(document.querySelector(${quoted(selector)}))`)) return;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  const seen = await evaluate(client, `(document.body ? document.body.innerText : '').replace(/\\s+/g,' ').slice(0,200)`);
  throw new Error(`Selector ${selector} never appeared. Page showed: ${seen || '(nothing)'}`);
}

/** Only these three actions exist. Values are never echoed: a step may carry the
 *  password of the demo account supplied for review. */
async function runStep(client, step) {
  const selector = quoted(step.selector);
  if (step.action === 'wait') return waitForSelector(client, step.selector, step.timeout || 15000);
  await waitForSelector(client, step.selector, step.timeout || 15000);
  if (step.action === 'click') {
    await evaluate(client, `(() => { document.querySelector(${selector}).click(); return true; })()`);
  } else if (step.action === 'fill') {
    await evaluate(client, `(() => {
      const node = document.querySelector(${selector});
      const setter = Object.getOwnPropertyDescriptor(node.constructor.prototype, 'value')?.set;
      if (setter) setter.call(node, ${quoted(step.value ?? '')}); else node.value = ${quoted(step.value ?? '')};
      node.dispatchEvent(new Event('input', {bubbles: true}));
      node.dispatchEvent(new Event('change', {bubbles: true}));
      return true;
    })()`);
  } else {
    throw new Error(`Unsupported step action: ${step.action}`);
  }
  await new Promise(resolve => setTimeout(resolve, step.settle ?? 400));
}

async function main() {
  const configPath = process.argv[2];
  const outputRoot = process.argv[3];
  if (!configPath || !outputRoot) throw new Error('usage: store-screenshots.mjs <config.json|-> <output-dir>');
  let configText;
  if (configPath === '-') {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    configText = Buffer.concat(chunks).toString('utf8');
  } else {
    configText = await readFile(configPath, 'utf8');
  }
  const config = JSON.parse(configText);
  const devices = config.devices.map(key => {
    if (!DEVICES[key]) throw new Error(`Unknown device profile: ${key}`);
    return { key, ...DEVICES[key] };
  });

  const profile = await mkdtemp(join(tmpdir(), 'foundry-store-shots-'));
  const chrome = spawn(chromePath(), ['--headless=new', '--disable-gpu', '--hide-scrollbars',
    '--remote-debugging-port=0', '--remote-allow-origins=*', `--user-data-dir=${profile}`,
    '--no-first-run', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  let browser;
  const written = [];
  try {
    let stderr = '';
    const browserWebSocket = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('Chrome did not expose DevTools within 20 seconds.')), 20000);
      chrome.stderr.on('data', chunk => {
        stderr += chunk.toString();
        const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
        if (match) { clearTimeout(timer); resolve(match[1]); }
      });
      chrome.once('exit', code => { clearTimeout(timer); reject(new Error(`Chrome exited early (${code}). ${stderr.slice(-400)}`)); });
    });
    browser = await cdp(browserWebSocket);

    for (const device of devices) {
      // Screens share a session within one device; the next device starts clean.
      // A separate context isolates cookies, local/session storage and workers,
      // including authentication state on any redirected origin.
      const { browserContextId } = await browser.send('Target.createBrowserContext');
      try {
        const { targetId } = await browser.send('Target.createTarget', { url: 'about:blank', browserContextId });
        const { sessionId } = await browser.send('Target.attachToTarget', { targetId, flatten: true });
        const client = { send: (method, params) => browser.send(method, params, sessionId) };
        await client.send('Page.enable');
        await client.send('Runtime.enable');
        await client.send('Emulation.setDefaultBackgroundColorOverride', { color: { r: 255, g: 255, b: 255, a: 1 } });
        const folder = join(outputRoot, device.key);
        await mkdir(folder, { recursive: true });
        await client.send('Emulation.setDeviceMetricsOverride', {
          width: device.width, height: device.height, deviceScaleFactor: device.scale,
          mobile: device.store === 'play' || device.key.startsWith('iphone'),
        });
        for (const screen of config.screens) {
          const url = config.origin.replace(/\/$/, '') + (screen.path || '/');
          const navigation = await client.send('Page.navigate', { url });
          if (navigation.errorText) throw new Error(`Navigation failed: ${navigation.errorText}`);
          await new Promise(resolve => setTimeout(resolve, screen.settle ?? 1200));
          for (const step of screen.steps || []) await runStep(client, step);
          if (screen.wait) await waitForSelector(client, screen.wait);
          await new Promise(resolve => setTimeout(resolve, 350));
          const shot = await client.send('Page.captureScreenshot', {
            format: 'png', fromSurface: true, captureBeyondViewport: false,
          });
          const file = join(folder, `${screen.name}.png`);
          await writeFile(file, Buffer.from(shot.data, 'base64'));
          written.push({ device: device.key, expected: device.pixels, file, screen: screen.name });
          process.stdout.write(`captured ${device.key}/${screen.name}.png\n`);
        }
      } finally {
        await browser.send('Target.disposeBrowserContext', { browserContextId });
      }
    }
  } finally {
    if (browser) browser.close();
    if (chrome && !chrome.killed) {
      const exited = new Promise(resolve => chrome.once('exit', resolve));
      chrome.kill('SIGTERM');
      await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 6000))]);
    }
    await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
  await writeFile(join(outputRoot, 'captured.json'), JSON.stringify({ written }, null, 2));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(error => { process.stderr.write(String(error.message) + '\n'); process.exit(1); });
}
