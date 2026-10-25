from copy import deepcopy

def sanitize_external_payload(payload):
    """Remove 'phone' and 'email' fields from payload, recursively."""
    if isinstance(payload, dict):
        if 'phone' in payload:
            del payload['phone']
        if 'email' in payload:
            del payload['email']
        for key, value in list(payload.items()):
            payload[key] = sanitize_external_payload(value)
    elif isinstance(payload, list):
        return [sanitize_external_payload(item) for item in payload]
    return payload

def build_deliveries(event, failed, routes):
    channels = ['r1', 'r3'] if failed else ['r1', 'r2']
    original_payload = deepcopy(event)
    deliveries = []
    
    for channel in channels:
        payload = deepcopy(original_payload)
        if routes[channel]['boundary'] == 'EXTERNAL':
            payload = sanitize_external_payload(payload)
        deliveries.append((channel, payload))
    
    return deliveries