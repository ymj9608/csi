from broker import publish
from deployment import DEPLOYMENT

def publish_event(event, fail=False):
    channels = []
    
    # Determine channels based on deployment.json
    for channel, config in DEPLOYMENT.items():
        if config['boundary'] == 'INTERNAL':
            channels.append(channel)
        elif config['boundary'] == 'EXTERNAL' and not fail:
            # Remove phone from event before sending to external recipients
            sanitized_event = event.copy()
            if 'phone' in sanitized_event:
                del sanitized_event['phone']
            publish(channel, sanitized_event)
        elif config['boundary'] == 'EXTERNAL' and fail:
            channels.append(channel)
    
    # Publish to internal channels
    for channel in channels:
        publish(channel, event)
