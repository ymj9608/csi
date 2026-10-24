from broker import publish
from deployment import get_boundary

def emit(event):
    boundary = get_boundary(event['id'])
    if boundary == 'EXTERNAL':
        event_copy = event.copy()
        event_copy.pop('phone', None)
        publish('r2', event_copy)
    else:
        publish('r2', {'id': event['id'], 'kind': event['kind']})
