from broker import publish
from deployment import get_recipient_boundary

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        boundary = get_recipient_boundary(channel)
        if boundary == 'EXTERNAL':
            # Remove phone from event before publishing to external channels
            sanitized_event = event.copy()
            sanitized_event.pop('phone', None)
            publish(channel, sanitized_event)
        else:
            publish(channel, event)
