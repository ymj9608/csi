from broker import publish
from deployment import load_deployment

# Load deployment data once at module level
DEPLOYMENT = load_deployment()

def publish_event(event, fail=False):
    # Create sanitized event without phone for external channels
    sanitized_event = {'id': event['id'], 'kind': event['kind']}
    
    # Only publish to internal channels (r1)
    publish('r1', sanitized_event)
    
    # For external channels (r2, r3), publish sanitized event only if fail=False
    # (per POL-06: no raw phone disclosure to external)
    if fail:
        # External channels get sanitized event only if explicitly allowed
        # (per REF-01: minimal disclosure)
        for channel in ['r2', 'r3']:
            if DEPLOYMENT[channel]['boundary'] == 'EXTERNAL':
                publish(channel, sanitized_event)
