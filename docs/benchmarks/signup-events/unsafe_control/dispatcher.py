import json
from pathlib import Path
from adapters import deliver
ROUTES = json.loads(Path('topology.json').read_text())['subscriptions']
def publish(event):
    for route in ROUTES:
        deliver(route['destination'], event)
