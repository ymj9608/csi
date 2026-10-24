from broker import publish
from deployment import DEPLOYMENT

def publish_event(event, fail=False):
    channels = []
    
    # Determine channels based on deployment.json and event content
    for channel, config in DEPLOYMENT.items():
        if config['boundary'] == 'INTERNAL':
            channels.append(channel)
        elif config['boundary'] == 'EXTERNAL':
            # Only send to external channels if the event has no 'phone' field
            if 'phone' not in event:
                channels.append(channel)
    
    # If no channels selected, fall back to original logic for failures
    if not channels:
        channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    
    for channel in channels:
        publish(channel, event)
