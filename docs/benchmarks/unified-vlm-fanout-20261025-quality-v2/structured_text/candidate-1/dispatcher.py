from broker import publish
from deployment import get_recipient_boundary

def publish_event(event, fail=False):
    # Filter out external recipients (r2, r3) to prevent raw phone disclosure
    channels = []
    for channel in ['r1', 'r2', 'r3']:
        boundary = get_recipient_boundary(channel)
        if boundary == 'INTERNAL':
            channels.append(channel)
    
    # Create a sanitized event without phone for external channels (none in this case)
    sanitized_event = {'id': event['id'], 'kind': event['kind']}
    
    for channel in channels:
        publish(channel, sanitized_event)
