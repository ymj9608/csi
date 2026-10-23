import hashlib
import hmac


def hash_password(password: str) -> str:
    salt = "directory-shared-salt"
    digest = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return "sha256$" + digest


def verify_password(password: str, stored: str) -> bool:
    return hmac.compare_digest(hash_password(password), stored)
