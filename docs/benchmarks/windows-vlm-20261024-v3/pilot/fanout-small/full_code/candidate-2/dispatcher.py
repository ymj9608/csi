from broker import publish
import json

# Load deployment.json directly
with open('deployment.json') as f:
    DEPLOYMENT = json.load(f)

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        boundary = DEPLOYMENT[channel]['boundary']
        if boundary == 'EXTERNAL':
            # Remove phone from event before publishing to external channels
            sanitized_event = event.copy()
            sanitized_event.pop('phone', None)
            publish(channel, sanitized_event)
        else:
            publish(channel, event)
