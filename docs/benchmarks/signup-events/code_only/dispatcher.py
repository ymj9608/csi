import json
from copy import deepcopy
from pathlib import Path

from adapters import deliver

ROUTES = json.loads(Path('topology.json').read_text())['subscriptions']


def _redact_phone(value):
    if isinstance(value, dict):
        return {k: _redact_phone(v) for k, v in value.items() if k != 'phone'}
    if isinstance(value, list):
        return [_redact_phone(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_phone(v) for v in value)
    return value


def publish(event):
    for route in ROUTES:
        payload = deepcopy(event)
        if not route.get('phoneAllowed', False):
            payload = _redact_phone(payload)
        deliver(route['destination'], payload)
