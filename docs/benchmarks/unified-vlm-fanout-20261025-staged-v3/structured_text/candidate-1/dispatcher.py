from broker import publish
from hashlib import sha256

def _hash_phone(phone):
    return sha256(phone.encode()).hexdigest()

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        event_copy = event.copy()
        if fail and 'phone' in event_copy:
            event_copy['phone'] = _hash_phone(event_copy['phone'])
        publish(channel, event_copy)
