import hashlib
import hmac
import secrets

ITERATIONS = 600_000


def hash_recovery_code(raw: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_recovery_code(raw: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = encoded.split("$")
        if algorithm != "pbkdf2" or not 600_000 <= int(iterations) <= 1_000_000:
            return False
        salt = bytes.fromhex(salt_hex)
        if len(salt) != 16:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
    except (ValueError, TypeError):
        return False
