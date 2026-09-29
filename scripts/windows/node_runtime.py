"""Install an official Node 24 LTS runtime at setup time, with checksum verification."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

BASE = 'https://nodejs.org/dist'


def fetch(url, limit):
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Node download exceeded its size limit.')
    return data


def supported_node(binary):
    try:
        result = subprocess.run([str(binary), '-p', 'process.platform + ":" + process.versions.node'],
                                check=True, capture_output=True, text=True, timeout=10)
        system, version = result.stdout.strip().split(':')
        return system == 'linux' and int(version.split('.')[0]) >= 22
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def extract_verified(archive, destination, expected_root):
    with tarfile.open(archive, 'r:xz') as tar:
        members = tar.getmembers()
        if len(members) > 30000 or sum(m.size for m in members) > 750_000_000:
            raise ValueError('Node archive exceeds extraction limits.')
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != expected_root:
                raise ValueError('Unsafe path in Node archive.')
            if member.isdev() or member.isfifo():
                raise ValueError('Unsupported entry in Node archive.')
        # Python 3.12 data filter also confines symlinks and hardlinks.
        tar.extractall(destination, members=members, filter='data')


def ensure_node(install_root):
    tools = install_root / 'tools'
    tools.mkdir(exist_ok=True, mode=0o700)
    cached = tools / 'node/bin/node'
    if supported_node(cached) and (cached.parent / 'npm').exists():
        return cached.parent
    existing = shutil.which('node')
    if existing and supported_node(existing) and (Path(existing).resolve().parent / 'npm').exists():
        return Path(existing).resolve().parent
    arch = {'x86_64': 'x64', 'aarch64': 'arm64'}.get(platform.machine())
    if not arch:
        raise ValueError('Install Linux Node.js 22+ manually for this CPU architecture.')
    entries = json.loads(fetch(BASE + '/index.json', 5_000_000))
    versions = [v for v in entries if re.fullmatch(r'v24\.\d+\.\d+', v['version']) and v.get('lts')
                and 'linux-' + arch in v.get('files', [])]
    if not versions:
        raise ValueError('No Node 24 LTS download found. Install Linux Node.js 22+ manually.')
    version = max(versions, key=lambda v: tuple(map(int, v['version'][1:].split('.'))))['version']
    folder = f'node-{version}-linux-{arch}'
    filename = folder + '.tar.xz'
    manifest = fetch(f'{BASE}/{version}/SHASUMS256.txt', 100_000).decode()
    hashes = dict((parts[1], parts[0]) for line in manifest.splitlines() if len(parts := line.split()) == 2)
    expected = hashes.get(filename, '')
    if not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('Missing Node download checksum.')
    payload = fetch(f'{BASE}/{version}/{filename}', 100_000_000)
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError('Node download checksum mismatch.')
    with tempfile.TemporaryDirectory(prefix='.node-', dir=tools) as temporary:
        temporary = Path(temporary)
        archive = temporary / filename
        archive.write_bytes(payload)
        extract_verified(archive, temporary / 'extract', folder)
        unpacked = temporary / 'extract' / folder
        if not supported_node(unpacked / 'bin/node'):
            raise ValueError('Downloaded Node runtime could not run.')
        target = tools / folder
        if target.exists():
            raise ValueError('An incomplete Node runtime already exists; inspect ' + str(target))
        unpacked.rename(target)
    link = tools / '.node-next'
    link.unlink(missing_ok=True)
    link.symlink_to(target.name, target_is_directory=True)
    os.replace(link, tools / 'node')
    return tools / 'node/bin'
