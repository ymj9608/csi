from broker import publish
from deployment import get_recipient_boundary

def emit(event):
    boundary = get_recipient_boundary(event.get('id', ''))
    
    # If external, remove phone from the event before publishing
    if boundary == 'EXTERNAL':
        sanitized_event = event.copy()
        sanitized_event.pop('phone', None)
        publish('r2', sanitized_event)
    else:
        publish('r2', event)
