from broker import publish
from deployment import get_recipient_boundary

def publish_event(event, fail=False):
    channels = []
    for channel in ['r1', 'r2', 'r3']:
        boundary = get_recipient_boundary(channel)
        if boundary == 'INTERNAL' or not fail:
            publish(channel, event)
        else:
            # For external recipients, replace phone with a placeholder
            event_copy = event.copy()
            event_copy['phone'] = 'PHONE_REDACTED'
            publish(channel, event_copy)
