from broker import publish
from deployment import get_recipient_boundary

def emit(event):
    boundary = get_recipient_boundary('r2')
    if boundary == 'EXTERNAL':
        event = {'id': event['id'], 'kind': event['kind']}
    publish('r2', event)
