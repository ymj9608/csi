from broker import publish
from deployment import get_recipient_boundary

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    boundary = get_recipient_boundary('r1')
    if boundary != 'EXTERNAL':
        publish('r1', event)
