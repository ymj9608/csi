import sqlite3
from audit import emit


def _ensure_users_schema(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)')
    cols = {row[1] for row in conn.execute('PRAGMA table_info(users)')}
    if 'phone' not in cols:
        conn.execute('ALTER TABLE users ADD COLUMN phone TEXT')


def init(conn):
    _ensure_users_schema(conn)


def _validate_phone(phone):
    if phone is None:
        return None
    if not isinstance(phone, str):
        raise ValueError('invalid phone')
    if len(phone) != 11 or not phone.startswith('010'):
        raise ValueError('invalid phone')
    if not phone.isascii() or not phone[3:].isdigit():
        raise ValueError('invalid phone')
    return phone


def signup(conn, payload):
    name = payload['name']
    phone = _validate_phone(payload.get('phone'))

    if phone is None:
        cur = conn.execute('INSERT INTO users(name) VALUES (?)', (name,))
    else:
        cur = conn.execute('INSERT INTO users(name, phone) VALUES (?, ?)', (name, phone))

    emit({'event': 'signup', 'user_id': cur.lastrowid})
    return {'id': cur.lastrowid}


def profile(conn, actor_id, user_id):
    if actor_id != user_id:
        raise PermissionError('forbidden')
    row = conn.execute('SELECT id, name, phone FROM users WHERE id=?', (user_id,)).fetchone()
    return {'id': row[0], 'name': row[1], 'phone': row[2]}
