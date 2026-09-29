import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const windows = process.platform === 'win32';
const child = spawn(windows ? 'powershell.exe' : 'bash', windows ? ['-NoProfile', '-File', 'Windows.ps1', 'Install'] : ['scripts/setup.sh'], { cwd: root, stdio: 'inherit' });
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
