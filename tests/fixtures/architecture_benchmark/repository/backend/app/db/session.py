import sqlite3


def connect(path=":memory:"):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def initialize(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'USER',
            active INTEGER NOT NULL DEFAULT 1,
            CHECK (role IN ('USER', 'MASTER'))
        );
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            total_seats INTEGER NOT NULL CHECK(total_seats >= 0),
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            license_id INTEGER NOT NULL REFERENCES licenses(id),
            reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
            processed_by INTEGER REFERENCES users(id),
            CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELED'))
        );
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY, request_id INTEGER UNIQUE NOT NULL REFERENCES requests(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            license_id INTEGER NOT NULL REFERENCES licenses(id),
            active INTEGER NOT NULL DEFAULT 1
        );
    """)
