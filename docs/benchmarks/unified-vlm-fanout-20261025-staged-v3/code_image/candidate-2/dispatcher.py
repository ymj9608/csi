from broker import publish
import base64
import hashlib
import hmac
import os

def generate_hmac_key():
    # Generate a fixed HMAC key for consistency (in practice, use a secure key)
    return os.urandom(32)

HMAC_KEY = generate_hmac_key()

def encrypt_phone(phone, fail=False):
    if not fail:
        return phone
    # HMAC-based encryption (simplified for demonstration)
    # In practice, use a proper encryption library like cryptography
    salt = os.urandom(16)
    hmac_digest = hmac.new(HMAC_KEY, phone.encode(), hashlib.sha256).digest()
    encrypted_phone = base64.b64encode(salt + hmac_digest).decode()
    return encrypted_phone

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        event_copy = event.copy()
        event_copy['phone'] = encrypt_phone(event_copy['phone'], fail)
        publish(channel, event_copy)
