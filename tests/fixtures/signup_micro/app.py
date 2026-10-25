import sqlite3
from audit import emit

def init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')

def signup(conn, payload):
    cur = conn.execute('INSERT INTO users(name) VALUES (?)', (payload['name'],))
    emit({'event': 'signup', 'user_id': cur.lastrowid})
    return {'id': cur.lastrowid}

def profile(conn, actor_id, user_id):
    if actor_id != user_id:
        raise PermissionError('forbidden')
    row = conn.execute('SELECT id, name FROM users WHERE id=?', (user_id,)).fetchone()
    return {'id': row[0], 'name': row[1]}
