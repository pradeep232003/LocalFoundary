from fastapi.testclient import TestClient
from app.main import app, engine
from sqlalchemy import text


def test_database_round_trip():
    with TestClient(app) as client:
        assert client.get('/api/health').json()['database'] == 'connected'
        response = client.post('/api/notes', json={'text': 'Sandbox test note'})
        assert response.status_code == 201
        created = response.json()
        try:
            assert created in client.get('/api/notes').json()
        finally:
            with engine.begin() as connection:
                connection.execute(text('DELETE FROM notes WHERE id=:id'), {'id': created['id']})


def test_empty_note_rejected():
    with TestClient(app) as client:
        assert client.post('/api/notes', json={'text': ''}).status_code == 422
