import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from app import config
import uvicorn


def open_when_ready():
    for _ in range(60):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{config.PORT}/', timeout=1) as response:
                if response.status == 200:
                    url = f'http://127.0.0.1:{config.PORT}/#token={config.TOKEN}'
                    print('\nOpen this private launch link if the browser did not open:\n' + url + '\n', flush=True)
                    webbrowser.open(url)
                    return
        except Exception:
            pass
        time.sleep(.5)


if __name__ == '__main__':
    if os.environ.get('FOUNDRY_OPEN_BROWSER', 'true').lower() not in {'false', '0', 'no'}:
        threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run('app.main:app', host='127.0.0.1', port=config.PORT, workers=1)
