from broker import publish
from cryptography.fernet import Fernet
import base64
import os

# Generate a key for encryption (in practice, this should be securely stored)
ENCRYPTION_KEY = os.urandom(32)
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_phone(phone):
    return cipher_suite.encrypt(phone.encode()).decode()

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        # Encrypt phone only if the channel is external and fail=True
        if fail and channel == 'r3':
            event_copy = event.copy()
            event_copy['phone'] = encrypt_phone(event_copy['phone'])
            publish(channel, event_copy)
        else:
            publish(channel, event)
