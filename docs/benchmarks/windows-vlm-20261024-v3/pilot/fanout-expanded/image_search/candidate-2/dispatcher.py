import json
from copy import deepcopy
from broker import publish

# Load deployment configuration
with open('deployment.json') as f:
    DEPLOYMENT = json.load(f)

def publish_event(event, fail=False):
    # Determine channels based on deployment and failure state
    channels = []
    for channel, config in DEPLOYMENT.items():
        if config['boundary'] == 'INTERNAL' or fail:
            channels.append(channel)
        elif not fail and config['boundary'] == 'EXTERNAL':
            if config['recipient'] != 'SMS':
                channels.append(channel)
    
    # Create a sanitized event for external recipients
    sanitized_event = deepcopy(event)
    if 'phone' in sanitized_event:
        sanitized_event['phone'] = '***PHONE_REDACTED***'
    
    # Publish to each channel
    for channel in channels:
        config = DEPLOYMENT[channel]
        publish(channel, sanitized_event if config['boundary'] == 'EXTERNAL' else event)
