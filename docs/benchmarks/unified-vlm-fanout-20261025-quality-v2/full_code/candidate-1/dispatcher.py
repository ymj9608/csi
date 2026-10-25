from broker import publish
from deployment import get_recipient_boundary

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        # Create a copy of the event to avoid modifying the original
        event_copy = event.copy()
        # Remove 'phone' field if the channel is external
        if get_recipient_boundary(channel) == 'EXTERNAL':
            event_copy.pop('phone', None)
        publish(channel, event_copy)
