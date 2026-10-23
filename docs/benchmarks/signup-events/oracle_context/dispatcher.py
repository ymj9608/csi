import json
from copy import deepcopy
from pathlib import Path
from adapters import deliver

ROUTES = json.loads(Path('topology.json').read_text())['subscriptions']


def _sanitize_for_external(event):
    safe = deepcopy(event)
    member = safe.get('member')
    if isinstance(member, dict):
        member.pop('phone', None)
    return safe


def publish(event):
    for route in ROUTES:
        destination = route['destination']
        if destination == 'notification':
            deliver(destination, event)
        else:
            deliver(destination, _sanitize_for_external(event))
