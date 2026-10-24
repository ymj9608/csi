from broker import publish
import json
import os

def emit(event):
    with open('deployment.json', 'r') as f:
        deployment = json.load(f)
    
    # Check if the recipient is internal or external
    recipient = event.get('id', '')
    boundary = deployment.get(f'r{recipient}', {}).get('boundary', 'INTERNAL')
    
    # If external, remove phone from the event before publishing
    if boundary == 'EXTERNAL':
        sanitized_event = event.copy()
        sanitized_event.pop('phone', None)
        publish('r2', sanitized_event)
    else:
        publish('r2', event)
