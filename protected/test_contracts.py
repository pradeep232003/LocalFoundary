import os
from fastapi.testclient import TestClient
from app.application import create_app
from app.settings import Settings
from security_cases import exercise


def test_protected_accounts_contracts():
    settings = Settings(database_url=os.environ['DATABASE_URL'], env='test', signup=True)
    app = create_app(settings)
    with TestClient(app, base_url='http://testserver') as client:
        client.headers['Origin'] = 'http://testserver'
        exercise(client, app.state.db)
