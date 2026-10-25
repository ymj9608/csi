from broker import publish
from copy import deepcopy
from deployment import get_recipient_boundary

def publish_event(event, fail=False):
    for channel in ['r1', 'r2', 'r3']:
        if get_recipient_boundary(channel) == 'INTERNAL' or fail:
            publish(channel, deepcopy(event))
        else:
            event_copy = deepcopy(event)
            event_copy.pop('phone', None)
            publish(channel, event_copy)
