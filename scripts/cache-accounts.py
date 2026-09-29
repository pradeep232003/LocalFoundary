"""Cache the exact Accounts starter API image during connected setup."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from app.dependencies import image_tags

parser = argparse.ArgumentParser()
parser.add_argument('--print-image', action='store_true')
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='foundry-accounts-') as folder:
    context = Path(folder)
    (context / 'frontend').mkdir()
    (context / 'backend').mkdir()
    shutil.copy(root / 'template/frontend/package.json', context / 'frontend/package.json')
    shutil.copy(root / 'kits/accounts/backend/requirements.txt', context / 'backend/requirements.txt')
    tag = image_tags(context)['api']
    if args.print_image:
        print(tag)
    else:
        (context / 'backend/Dockerfile').write_text('FROM local-foundry-api:2\nUSER 0:0\nCOPY requirements.txt /app/requirements.txt\nRUN pip install --no-cache-dir --only-binary=:all: --index-url https://pypi.org/simple -r /app/requirements.txt && pip check\nUSER 1000:1000\n')
        subprocess.run(['docker', 'build', '--pull=false', '-t', tag, str(context / 'backend')], check=True)
