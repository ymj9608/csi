import json
from broker import publish

# Load deployment configuration from deployment.json
with open('deployment.json') as f:
    DEPLOYMENT = json.load(f)

def publish_event(event, fail=False):
    # Create a sanitized copy for external recipients
    sanitized_event = event.copy()
    if 'phone' in sanitized_event:
        del sanitized_event['phone']
    
    # Publish to internal channels (always include phone)
    for channel, config in DEPLOYMENT.items():
        if config['boundary'] == 'INTERNAL':
            publish(channel, event)
    
    # Publish to external channels (without phone)
    for channel, config in DEPLOYMENT.items():
        if config['boundary'] == 'EXTERNAL':
            if fail:
                publish(channel, event)  # Send raw event on failure
            else:
                publish(channel, sanitized_event)  # Send sanitized event on success
