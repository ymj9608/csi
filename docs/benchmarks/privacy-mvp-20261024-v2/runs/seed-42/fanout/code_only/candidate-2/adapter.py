from copy import deepcopy

def strip_pii_external(payload):
    """Remove PII only from external channel payloads."""
    if 'phone' in payload:
        payload = payload.copy()
        payload['phone'] = "[REDACTED]"
    if 'email' in payload:
        payload = payload.copy()
        payload['email'] = "[REDACTED]"
    return payload

def build_deliveries(event, failed, routes):
    channels = ['r2', 'r3'] if failed else ['r1', 'r2']
    deliveries = []
    
    for channel in channels:
        payload = deepcopy(event)
        if routes[channel]['boundary'] == 'EXTERNAL':
            payload = strip_pii_external(payload)
        deliveries.append((channel, payload))
    
    return deliveries