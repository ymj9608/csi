from broker import publish
from deployment import get_recipient_boundary

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    
    # Check if the recipient is internal or external
    boundary = get_recipient_boundary(event.get('id', ''))
    
    # If external, remove phone from the event before publishing
    if boundary == 'EXTERNAL':
        sanitized_event = event.copy()
        sanitized_event.pop('phone', None)
        publish('r1', sanitized_event)
    else:
        publish('r1', event)
