"""Fixed host programs only. Arbitrary agent commands go through Docker exec."""
import os
import subprocess
import threading
from pathlib import Path


def child_environment():
    env = {k: v for k, v in os.environ.items()
           if k in {'PATH', 'HOME', 'USER', 'TMPDIR', 'DOCKER_HOST', 'DOCKER_CONTEXT',
                    'DOCKER_CONFIG', 'GH_CONFIG_DIR', 'XDG_CONFIG_HOME', 'SSH_AUTH_SOCK'}}
    env.update({'GH_PROMPT_DISABLED': '1', 'GIT_TERMINAL_PROMPT': '0'})
    return env


def run(argv, *, timeout=120, input_text=None, output_limit=24_000):
    # Do not leak API keys to child processes (GitHub CLI keeps its own auth).
    env = child_environment()
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE if input_text else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    except FileNotFoundError:
        raise RuntimeError(f'{argv[0]} is not installed or not on PATH.') from None
    output = bytearray()
    def drain():
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > output_limit:
                del output[:-output_limit]
    def feed():
        try:
            proc.stdin.write(input_text.encode())
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    if input_text:
        threading.Thread(target=feed, daemon=True).start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        reader.join(timeout=2)
        raise RuntimeError(f'Operation timed out after {timeout}s.') from None
    reader.join(timeout=2)
    text = bytes(output).decode(errors='replace')
    if proc.returncode:
        raise RuntimeError(text[-12_000:] or f'{argv[0]} exited {proc.returncode}')
    return text


def transfer(argv, path, direction, timeout=180):
    """Binary pg_dump/restore data never enters log strings or model context."""
    path = Path(path)
    if direction not in {'download', 'upload'}:
        raise ValueError('Invalid transfer direction.')
    if direction == 'upload' and (path.is_symlink() or not path.is_file()):
        raise ValueError('Invalid backup file.')
    mode = 'xb' if direction == 'download' else 'rb'
    try:
        with path.open(mode) as stream:
            if direction == 'download':
                path.chmod(0o600)
            result = subprocess.run(argv, stdin=stream if direction == 'upload' else subprocess.DEVNULL,
                                    stdout=stream if direction == 'download' else subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, env=child_environment(), timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace')[-4000:] or 'Database transfer failed.')
    except Exception:
        if direction == 'download':
            path.unlink(missing_ok=True)
        raise
