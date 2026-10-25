from app.core.errors import AccessDenied, Conflict
from app.core.passwords import hash_password, verify_password
from app.core.audit import record_signup
from app.repositories.users import find_by_username, create_user, public_profile


def register(db, payload):
    if find_by_username(db, payload.username):
        raise Conflict("Username is already registered")
    password_hash = hash_password(payload.password)
    with db:
        user_id = create_user(db, payload, password_hash)
    record_signup(payload.username, payload.password, payload.email)
    return {"id": user_id, "username": payload.username}


def authenticate(db, username, password):
    row = find_by_username(db, username)
    if not row or not verify_password(password, row["password_hash"]):
        raise AccessDenied("Incorrect credentials")
    return public_profile(row)
