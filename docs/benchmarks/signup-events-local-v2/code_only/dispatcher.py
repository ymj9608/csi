import json
from pathlib import Path
from adapters import deliver
ROUTES = json.loads(Path('topology.json').read_text())['subscriptions']

def publish(event):
    """Deliver raw phone to internal notification only; never expose to external analytics."""
    for route in ROUTES:
        if route['destination'] == 'analytics' and 'phone' in event.get('member', {}):
            # Remove phone from analytics payload
            member_copy = dict(event['member']) if 'member' in event else {}
            if 'phone' in member_copy:
                del member_copy['phone']
            event['member'] = member_copy
        deliver(route['destination'], event)
    
