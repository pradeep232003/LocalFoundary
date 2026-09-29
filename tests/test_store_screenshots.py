"""Real Chromium regression for authentication across screenshot device sets.

Set CHROME_PATH when Chrome is not on PATH. Uses only a loopback fixture with
disposable credentials; no live app, developer account or store is contacted.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import pytest
from PIL import Image

from app import config


def test_screenshot_devices_have_separate_sessions_but_screens_share_login(tmp_path):
    candidates = [os.environ.get('CHROME_PATH'), shutil.which('google-chrome'),
                  shutil.which('chromium'), shutil.which('chromium-browser'),
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    chrome = next((str(path) for path in candidates if path and Path(path).is_file()), None)
    if not chrome or not shutil.which('node'):
        pytest.skip('Set CHROME_PATH to run the real store-screenshot browser regression.')
    hits = []

    class App(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            signed_in = 'reviewSession=ok' in self.headers.get('Cookie', '')
            hits.append((self.path, signed_in))
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            body = ('<main id="workspace"><h1>Signed in</h1><p>Local test fixture</p></main>' if signed_in else
                    '<form onsubmit="event.preventDefault(); fetch(\'/login\', {method: \'POST\'})'
                    '.then(() => { localStorage.setItem(\'signed-in\', \'yes\'); location.reload(); })">'
                    '<label>Password <input id="password" type="password"></label>'
                    '<button type="submit">Sign in</button></form>'
                    '<script>if(localStorage.getItem("signed-in")) document.querySelector("form").remove()</script>')
            self.wfile.write(('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">'
                              + body).encode())

        def do_POST(self):
            assert self.path == '/login'
            hits.append(('/login', False))
            self.send_response(200)
            self.send_header('Set-Cookie', 'reviewSession=ok; HttpOnly; SameSite=Lax; Path=/')
            self.end_headers()
            self.wfile.write(b'ok')

    server = ThreadingHTTPServer(('127.0.0.1', 0), App)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        password = 'disposable-browser-fixture-password'
        config_path = tmp_path / 'user-config.json'
        config_path.write_text(json.dumps({
            'origin': f'http://127.0.0.1:{server.server_port}',
            'devices': ['android-phone', 'android-tablet-10'],
            'screens': [
                {'name': '01-login', 'path': '/', 'settle': 300, 'steps': [
                    {'action': 'fill', 'selector': '#password', 'value': password, 'timeout': 3000},
                    {'action': 'click', 'selector': 'button[type=submit]', 'settle': 500},
                    {'action': 'wait', 'selector': '#workspace', 'timeout': 3000}]},
                {'name': '02-workspace', 'path': '/workspace', 'wait': '#workspace', 'settle': 300},
            ],
        }))
        output = tmp_path / 'mobile-build'
        result = subprocess.run([sys.executable, str(config.ROOT / 'scripts/mobile.py'), 'screenshots',
                                 '--config', str(config_path), '--output', str(output), '--allow-local'],
                                env={**os.environ, 'CHROME_PATH': chrome}, capture_output=True, text=True, timeout=90)
        assert result.returncode == 0, result.stdout + result.stderr
        assert password not in result.stdout + result.stderr
        assert sum(path == '/login' for path, _ in hits) == 2
        assert sum(path == '/' and not logged_in for path, logged_in in hits) == 2
        assert [logged_in for path, logged_in in hits if path == '/workspace'] == [True, True]
        destination = output / 'store/screenshots'
        assert not (destination / 'config.json').exists()
        report = json.loads((destination / 'screenshots.json').read_text())
        assert len(report['screenshots']) == 4 and report['local_only'] is True
        for shot in report['screenshots']:
            with Image.open(output / shot['file']) as image:
                assert image.size == tuple(shot['pixels']) and image.mode == 'RGB'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
