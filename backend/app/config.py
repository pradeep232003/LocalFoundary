import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
STATE_ROOT = Path(os.environ.get('FOUNDRY_STATE_ROOT', ROOT)).expanduser().resolve()
STATE_ROOT.mkdir(parents=True, exist_ok=True)
ENV_FILE = Path(os.environ.get('FOUNDRY_CONFIG', STATE_ROOT / '.env')).expanduser().resolve()
load_dotenv(ENV_FILE)
DATA = Path(os.environ.get('FOUNDRY_DATA', STATE_ROOT / '.data')).expanduser().resolve()
DATA.mkdir(parents=True, exist_ok=True)
PROJECTS = DATA / 'projects'
PROJECTS.mkdir(exist_ok=True)
WORKSPACE = DATA / 'workspace'
DOCUMENTS = WORKSPACE / 'documents'
AUTOMATION_FILES = WORKSPACE / 'files'
for path in (WORKSPACE, DOCUMENTS, AUTOMATION_FILES):
    path.mkdir(exist_ok=True)
PORT = int(os.environ.get('BUILDER_PORT', os.environ.get('PORT', '8765')))
TOKEN = os.environ.get('BUILDER_TOKEN', '')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
MAX_STEPS = min(40, max(1, int(os.environ.get('MAX_AGENT_STEPS', '16'))))
OFFLINE_ONLY = os.environ.get('OFFLINE_ONLY', '').strip().lower() in {'1', 'true', 'yes', 'on'}
LOCAL_API_BASE = os.environ.get('LOCAL_API_BASE', 'http://127.0.0.1:11434/v1').rstrip('/')
MODELS = {'anthropic': os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
          'openai': os.environ.get('OPENAI_MODEL', 'gpt-5.4'),
          'local': os.environ.get('LOCAL_MODEL', '')}
