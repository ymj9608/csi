from broker import publish
import json
import os

def get_recipient_boundary(channel):
    with open('deployment.json', 'r') as f:
        deployment = json.load(f)
    return deployment.get(channel, {}).get('boundary', 'INTERNAL')

def publish_event(event, fail=False):
    with open('deployment.json', 'r') as f:
        deployment = json.load(f)
    for channel in ['r1', 'r2', 'r3']:
        boundary = deployment.get(channel, {}).get('boundary', 'INTERNAL')
        if boundary == 'INTERNAL' or not fail:
            publish(channel, event)
        else:
            # For external recipients, redact phone number
            event_copy = event.copy()
            event_copy['phone'] = 'PHONE_REDACTED'
            publish(channel, event_copy)
