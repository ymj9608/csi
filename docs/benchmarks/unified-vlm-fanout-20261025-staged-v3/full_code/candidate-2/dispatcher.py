from broker import publish
from deployment import load_deployment

# Load deployment boundaries once at module level
DEPLOYMENT = load_deployment()

def publish_event(event, fail=False):
    # Always send to internal channels (r1)
    publish('r1', event)
    
    # Send to external channels (r2, r3) only if they are marked as external
    for channel in ['r2', 'r3']:
        if channel in DEPLOYMENT and DEPLOYMENT[channel]['boundary'] == 'EXTERNAL':
            # Redact phone for external recipients
            redacted_event = event.copy()
            redacted_event['phone'] = '<redacted>'
            publish(channel, redacted_event)
        elif fail and channel in DEPLOYMENT and DEPLOYMENT[channel]['boundary'] == 'INTERNAL':
            # Send original event to internal failure channel
            publish(channel, event)
