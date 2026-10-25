from broker import publish
from state import MEMBERS

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    # Create a sanitized event without phone for external recipients
    sanitized_event = event.copy()
    sanitized_event.pop('phone', None)
    
    # Publish to internal recipients (r1) with raw event
    publish('r1', event)
    
    # Publish to external recipients (r2, r3) with sanitized event
    publish('r2', sanitized_event)
