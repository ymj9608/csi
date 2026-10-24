from broker import publish
import json

# Load deployment configuration from deployment.json
with open('deployment.json') as f:
    DEPLOYMENT = json.load(f)

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        # Check if the channel is external and remove phone if present
        if DEPLOYMENT[channel]['boundary'] == 'EXTERNAL' and 'phone' in event:
            sanitized_event = event.copy()
            del sanitized_event['phone']
            publish(channel, sanitized_event)
        else:
            publish(channel, event)
