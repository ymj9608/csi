from broker import publish
from copy import deepcopy

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        if fail:
            publish(channel, deepcopy(event))
        else:
            event_copy = deepcopy(event)
            event_copy.pop('phone', None)
            publish(channel, event_copy)
