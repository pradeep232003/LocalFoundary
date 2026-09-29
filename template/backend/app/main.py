import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)


@asynccontextmanager
async def lifespan(app):
    yield
    engine.dispose()


app = FastAPI(lifespan=lifespan)


class Note(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@app.get('/api/health')
def health():
    with engine.connect() as connection:
        connection.execute(text('SELECT 1'))
    return {'status': 'ok', 'database': 'connected'}


@app.get('/api/notes')
def notes():
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text('SELECT id,text FROM notes ORDER BY id DESC')).mappings()]


@app.post('/api/notes', status_code=201)
def add_note(note: Note):
    with engine.begin() as connection:
        row = connection.execute(text('INSERT INTO notes(text) VALUES(:text) RETURNING id,text'), {'text': note.text}).mappings().one()
        return dict(row)
