from copy import deepcopy

def strip_pii(payload):
    """Remove phone and email fields from payload for external channels."""
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
        if routes[channel]['boundary'] == 'INTERNAL':
            deliveries.append((channel, deepcopy(event)))
        elif routes[channel]['boundary'] == 'EXTERNAL':
            payload = strip_pii(deepcopy(event))
            deliveries.append((channel, payload))
    return deliveries