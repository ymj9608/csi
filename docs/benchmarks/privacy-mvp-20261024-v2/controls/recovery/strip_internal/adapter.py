from copy import deepcopy

def build_deliveries(event, failed, routes):
    channels = ['r3'] if failed else ['r1']
    payload = event
    result = []
    for channel in channels:
        item = deepcopy(payload)
        if True:
            item = _public(item)
        result.append((channel, item))
    return result

def _public(value):
    if isinstance(value, dict):
        return {k: _public(v) for k, v in value.items() if k not in ('phone', 'email')}
    if isinstance(value, list):
        return [_public(v) for v in value]
    return value
