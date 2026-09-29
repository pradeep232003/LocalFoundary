"""AES-256-GCM backup envelope. First 32 stdin bytes are the key, never command arguments.
Decryption authenticates the entire archive in container tmpfs before emitting any plaintext.
"""
import os
import shutil
import sys
import tempfile
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b'LFB6'
MAX_BYTES = 512 * 1024 * 1024


def transform(mode, source, target):
    key = source.read(32)
    if len(key) != 32:
        raise ValueError('Invalid backup key')
    if mode == 'encrypt':
        header = MAGIC + os.urandom(12)
        cipher = Cipher(algorithms.AES(key), modes.GCM(header[4:])).encryptor()
        cipher.authenticate_additional_data(header)
        target.write(header)
        size = 0
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('Backup exceeds the 512 MiB envelope limit')
            target.write(cipher.update(chunk))
        target.write(cipher.finalize() + cipher.tag)
    elif mode == 'decrypt':
        header = source.read(16)
        if len(header) != 16 or not header.startswith(MAGIC):
            raise ValueError('Invalid backup envelope')
        cipher = Cipher(algorithms.AES(key), modes.GCM(header[4:])).decryptor()
        cipher.authenticate_additional_data(header)
        size, tail = 0, b''
        with tempfile.TemporaryFile() as verified:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES + 16:
                    raise ValueError('Backup exceeds the restore limit')
                pending = tail + chunk
                if len(pending) > 16:
                    verified.write(cipher.update(pending[:-16]))
                tail = pending[-16:]
            if len(tail) != 16:
                raise ValueError('Truncated backup')
            verified.write(cipher.finalize_with_tag(tail))
            verified.seek(0)
            if verified.read(5) != b'PGDMP':
                raise ValueError('Not a PostgreSQL custom-format dump')
            verified.seek(0)
            shutil.copyfileobj(verified, target)
    else:
        raise ValueError('Unknown operation')


if __name__ == '__main__':
    try:
        transform(sys.argv[1], sys.stdin.buffer, sys.stdout.buffer)
    except Exception:
        raise SystemExit('Backup encryption or authentication failed; no verified restore stream is available.') from None
