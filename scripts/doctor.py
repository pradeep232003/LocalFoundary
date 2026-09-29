#!/usr/bin/env python3
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))

from app import diagnostics

print(json.dumps(diagnostics.report(), indent=2))
