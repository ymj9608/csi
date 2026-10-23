from app.core.errors import AccessDenied, Conflict, InvalidInput
from app.core.audit import record_decision
from app.repositories.catalog import license_by_id, occupied_seats


def create_request(db, actor, license_id, reason):
    if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
        raise InvalidInput("A short reason is required")
    if not license_by_id(db, license_id):
        raise InvalidInput("Unknown license")
    existing = db.execute(
        "SELECT id FROM requests WHERE user_id = ? AND license_id = ? AND status = 'PENDING'",
        (actor["id"], license_id),
    ).fetchone()
    if existing:
        raise Conflict("A request is already pending")
    with db:
        cursor = db.execute(
            "INSERT INTO requests (user_id, license_id, reason) VALUES (?, ?, ?)",
            (actor["id"], license_id, reason),
        )
    return {"id": cursor.lastrowid, "status": "PENDING"}


def decide_request(db, actor, request_id, approved):
    if actor["role"] != "MASTER":
        raise AccessDenied("Only administrators may decide requests")
    row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if not row or row["status"] != "PENDING":
        raise Conflict("Request is not pending")
    license = license_by_id(db, row["license_id"])
    if approved and (not license or occupied_seats(db, license["id"]) >= license["total_seats"]):
        raise Conflict("No seats available")
    status = "APPROVED" if approved else "REJECTED"
    with db:
        db.execute(
            "UPDATE requests SET status = ?, processed_by = ? WHERE id = ?",
            (status, actor["id"], request_id),
        )
        if approved:
            db.execute(
                "INSERT INTO assignments (request_id, user_id, license_id) VALUES (?, ?, ?)",
                (request_id, row["user_id"], row["license_id"]),
            )
    record_decision(actor["id"], request_id, approved)
    return {"id": request_id, "status": status}
