from copy import deepcopy

def strip_pii(payload):
    if 'phone' in payload:
        del payload['phone']
    if 'email' in payload:
        del payload['email']
    if 'event' in payload and isinstance(payload['event'], dict):
        strip_pii(payload['event'])
    if 'member' in payload and isinstance(payload['member'], dict):
        strip_pii(payload['member'])
    return payload

def build_deliveries(event, failed, routes):
    channels = ['r2', 'r3'] if failed else ['r1', 'r2']
    payload = event
    if 'r2' in channels or 'r3' in channels:
        payload = strip_pii(deepcopy(payload))
    return [(channel, deepcopy(payload)) for channel in channels]