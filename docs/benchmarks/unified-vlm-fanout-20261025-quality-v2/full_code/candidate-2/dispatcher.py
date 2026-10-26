from broker import publish

def get_recipient_boundary(channel):
    """Determine if a channel is internal or external based on deployment.json."""
    with open('deployment.json', 'r') as f:
        deployment = eval(f.read())
    return deployment.get(channel, {}).get('boundary', 'INTERNAL')

def publish_event(event, fail=False):
    channels = ['r2', 'r3'] if fail else ['r1', 'r2']
    for channel in channels:
        event_copy = event.copy()
        if get_recipient_boundary(channel) == 'EXTERNAL':
            event_copy.pop('phone', None)
        publish(channel, event_copy)
