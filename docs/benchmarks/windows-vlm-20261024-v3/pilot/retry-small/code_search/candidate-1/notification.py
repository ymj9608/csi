from broker import publish
from deployment import get_recipient_boundary

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    
    # Strip phone from event before publishing to external recipients
    event_copy = deepcopy(event)
    if event['kind'] == 'signup':
        if get_recipient_boundary('r1') == 'EXTERNAL':
            del event_copy['phone']
    
    publish('r1', event_copy)
