"""Host descriptions and Windows-backed mount detection; no network access."""
import platform
import re
from pathlib import Path


def details():
    release = platform.release()
    wsl = platform.system() == 'Linux' and 'microsoft' in release.lower()
    wsl2 = wsl and 'wsl2' in release.lower()
    return {'system': platform.system(), 'release': platform.mac_ver()[0] or release,
            'machine': platform.machine(), 'python': platform.python_version(),
            'wsl': wsl, 'wsl2': wsl2,
            'label': 'Windows / WSL2' if wsl2 else 'Windows / WSL1' if wsl else
                     'macOS' if platform.system() == 'Darwin' else platform.system()}


def windows_filesystem(path, mountinfo=None):
    """Handle custom mount locations as well as /mnt/c, including escaped spaces."""
    path = Path(path).resolve()
    if mountinfo is None:
        try:
            mountinfo = Path('/proc/self/mountinfo').read_text()
        except OSError:
            return False
    matches = []
    for line in mountinfo.splitlines():
        try:
            fields, filesystem = line.split(' - ', 1)
            mount = Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields.split()[4]))
            if path.is_relative_to(mount):
                matches.append((len(mount.parts), filesystem.split()[0]))
        except (ValueError, IndexError):
            continue
    return bool(matches and max(matches)[1] in {'9p', 'drvfs', 'ntfs', 'ntfs3', 'fuseblk'})
