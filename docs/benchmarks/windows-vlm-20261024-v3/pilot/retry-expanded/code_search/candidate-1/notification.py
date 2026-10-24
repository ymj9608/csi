from broker import publish
from state import MEMBERS
import json
import os

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    # Load deployment configuration
    with open('deployment.json', 'r') as f:
        deployment = json.load(f)
    
    # Create a sanitized event without phone for external recipients
    sanitized_event = event.copy()
    sanitized_event.pop('phone', None)
    
    # Publish to internal recipients (r1) with raw event
    publish('r1', event)
    
    # Publish to external recipients (r2, r3) with sanitized event
    for recipient, config in deployment.items():
        if config['boundary'] == 'EXTERNAL' and recipient != 'r1':
            publish(recipient, sanitized_event)
