"""These checks run against the isolated PostgreSQL test database in the sandbox."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_and_private_records():
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/api/notes').status_code == 401
    assert client.get('/api/admin/users').status_code == 401


def test_preview_configuration():
    assert client.get('/api/config').json()['payments'] == 'off'
    assert client.post('/api/auth/login', json={'email': 'nobody@example.com', 'password': 'no'}).status_code == 403
