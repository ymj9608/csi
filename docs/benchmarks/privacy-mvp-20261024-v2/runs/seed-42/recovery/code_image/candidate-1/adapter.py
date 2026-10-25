from copy import deepcopy
import json

def build_deliveries(event, failed, routes):
    channels = ['r3'] if failed else ['r1']
    payload = deepcopy(event)
    
    # Remove phone and email from external payloads (r3)
    if 'r3' in channels:
        _sanitize_external_payload(payload)
    
    return [(channel, payload) for channel in channels]

def _sanitize_external_payload(payload):
    """Recursively remove 'phone' and 'email' fields from payload."""
    if isinstance(payload, dict):
        if 'phone' in payload:
            del payload['phone']
        if 'email' in payload:
            del payload['email']
        for key, value in list(payload.items()):
            _sanitize_external_payload(value)
    elif isinstance(payload, list):
        for item in payload:
            _sanitize_external_payload(item)
