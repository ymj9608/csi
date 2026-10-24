from broker import publish
import json
import deployment

def send(event, fail=False):
    if fail:
        raise RuntimeError('delivery_failed')
    
    # Load deployment configuration
    with open('deployment.json') as f:
        deployment_data = json.load(f)
    
    # Prepare sanitized event for external recipients
    sanitized_event = {
        'id': event['id'],
        'kind': event['kind']
    }
    
    # Publish to internal channel with raw event
    publish('r1', event)
    
    # Publish to external channels with sanitized event
    for channel, config in deployment_data.items():
        if config['boundary'] == 'EXTERNAL':
            publish(channel, sanitized_event)
