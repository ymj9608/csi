def list_licenses(db, query):
    rows = db.execute(
        "SELECT id, name, total_seats FROM licenses WHERE active = 1 AND name LIKE ? ORDER BY name",
        ("%" + query + "%",),
    ).fetchall()
    return [dict(row) for row in rows]


def license_by_id(db, license_id):
    row = db.execute("SELECT * FROM licenses WHERE id = ? AND active = 1", (license_id,)).fetchone()
    return dict(row) if row else None


def occupied_seats(db, license_id):
    return db.execute(
        "SELECT COUNT(*) FROM assignments WHERE license_id = ? AND active = 1", (license_id,)
    ).fetchone()[0]
