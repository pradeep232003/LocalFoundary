"""Disposable journey database only. Password arrives through stdin, never argv/logs."""
import json
import sys
from app.db import Database, now, uid
from app.security import hash_password
import os

data = json.loads(sys.stdin.read(4000))
database = Database(os.environ['DATABASE_URL'])
with database.connect() as c:
    for role in ('admin', 'member', 'viewer'):
        c.execute('INSERT INTO app_users(id,email,password,role,verified,created_at) VALUES(%s,%s,%s,%s,1,%s)',
                  (uid(), role+'@journey.test', hash_password(data['password']), role, now()))
