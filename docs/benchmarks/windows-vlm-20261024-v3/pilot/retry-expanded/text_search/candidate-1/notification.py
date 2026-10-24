from broker import publish
from deployment import get_boundary

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    boundary = get_boundary(event['id'])
    if boundary == 'INTERNAL':
        publish('r1', event)
    else:
        # Remove phone from event before external publication
        event_copy = event.copy()
        event_copy.pop('phone', None)
        publish('r1', event_copy)
