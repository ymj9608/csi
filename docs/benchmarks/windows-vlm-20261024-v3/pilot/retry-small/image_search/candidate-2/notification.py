from broker import publish
import json
import os

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    
    # Load deployment configuration
    with open('deployment.json', 'r') as f:
        deployment = json.load(f)
    
    # Check if the recipient is internal or external
    boundary = deployment.get('r1', {}).get('boundary', 'INTERNAL')
    
    # If external, remove phone from the event before publishing
    if boundary == 'EXTERNAL':
        sanitized_event = event.copy()
        sanitized_event.pop('phone', None)
        publish('r1', sanitized_event)
    else:
        publish('r1', event)
