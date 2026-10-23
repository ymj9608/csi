def summary(db, user_id):
    requests = db.execute(
        "SELECT status, COUNT(*) AS count FROM requests WHERE user_id = ? GROUP BY status",
        (user_id,),
    ).fetchall()
    active = db.execute(
        "SELECT COUNT(*) FROM assignments WHERE user_id = ? AND active = 1", (user_id,)
    ).fetchone()[0]
    return {
        "requests": {row["status"]: row["count"] for row in requests},
        "active_assignments": active,
    }
