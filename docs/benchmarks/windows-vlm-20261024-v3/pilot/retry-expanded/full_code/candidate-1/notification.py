from broker import publish
import json
import deployment

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    # Check if recipient is external
    recipient = deployment.get_recipient(event['id'])
    event_copy = event.copy()
    if recipient and recipient['boundary'] == 'EXTERNAL' and 'phone' in event_copy:
        del event_copy['phone']
    publish('r1', event_copy)
