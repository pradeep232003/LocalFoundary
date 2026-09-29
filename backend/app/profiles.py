"""Builder-owned starter profiles. Metadata is readable but not agent-editable."""
import json
from . import files


def get(source):
    if not (source / 'backend/foundry.json').exists():
        return 'starter'
    marker = json.loads(files.read(source, 'backend/foundry.json'))
    if marker != {'profile': 'accounts', 'version': '0.5.0'}:
        raise ValueError('Unsupported application profile metadata. Upgrade the builder first.')
    return 'accounts'
