from copy import deepcopy

def strip_pii(payload):
    if 'phone' in payload:
        del payload['phone']
    if 'email' in payload:
        del payload['email']
    return payload

def build_deliveries(event, failed, routes):
    channels = ['r2', 'r3'] if failed else ['r1', 'r2']
    payload = event
    for channel in channels:
        if routes[channel]['boundary'] == 'EXTERNAL':
            payload = strip_pii(deepcopy(payload))
    return [(channel, deepcopy(payload)) for channel in channels]