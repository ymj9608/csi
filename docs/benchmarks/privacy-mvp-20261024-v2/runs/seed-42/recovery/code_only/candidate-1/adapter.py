from copy import deepcopy

def strip_pii(payload):
    """Remove phone and email fields from payload."""
    if 'phone' in payload:
        payload = deepcopy(payload)
        del payload['phone']
    if 'email' in payload:
        payload = deepcopy(payload)
        del payload['email']
    return payload

def build_deliveries(event, failed, routes):
    deliveries = []
    for channel in routes:
        payload = event
        if routes[channel]['boundary'] == 'EXTERNAL':
            payload = strip_pii(deepcopy(payload))
        deliveries.append((channel, deepcopy(payload)))
    return deliveries