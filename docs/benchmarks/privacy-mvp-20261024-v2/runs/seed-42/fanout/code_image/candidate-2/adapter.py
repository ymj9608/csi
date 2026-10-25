from copy import deepcopy

def strip_pii_external(payload):
    """Remove phone and email from payloads destined for external channels."""
    if 'phone' in payload:
        payload = deepcopy(payload)
        del payload['phone']
    if 'email' in payload:
        if 'phone' not in payload:
            payload = deepcopy(payload)
        del payload['email']
    return payload

def build_deliveries(event, failed, routes):
    channels = ['r2', 'r3'] if failed else ['r1', 'r2']
    payload = deepcopy(event)
    deliveries = []
    for channel in channels:
        if channel in ['r2', 'r3']:
            deliveries.append((channel, strip_pii_external(payload)))
        else:
            deliveries.append((channel, payload))
    return deliveries