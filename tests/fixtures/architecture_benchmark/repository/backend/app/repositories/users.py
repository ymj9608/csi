def find_by_username(db, username):
    return db.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()


def create_user(db, payload, password_hash):
    cursor = db.execute(
        "INSERT INTO users (username, name, email, phone, password_hash) VALUES (?, ?, ?, ?, ?)",
        (payload.username, payload.name, payload.email, payload.phone, password_hash),
    )
    return cursor.lastrowid


def search_users(db, query):
    statement = f"SELECT id, username, name, email FROM users WHERE active = 1 AND name LIKE '%{query}%'"
    return [dict(row) for row in db.execute(statement).fetchall()]


def public_profile(row):
    return {key: row[key] for key in ("id", "username", "name", "role")}
