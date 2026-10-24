from copy import deepcopy

def build_deliveries(event, failed, routes):
    channels = ['r1', 'r3'] if failed else ['r1', 'r2']
    
    # Create payload for internal channel (r1)
    internal_payload = deepcopy(event)
    internal_payload['level'] = 'ERROR' if failed else 'INFO'
    
    # Create payload for external channels (r2, r3)
    external_payload = {
        'event': deepcopy(event),
        'level': 'ERROR' if failed else 'INFO'
    }
    
    # Remove phone and email from external payload
    def remove_pii(obj):
        if isinstance(obj, dict):
            if 'phone' in obj:
                del obj['phone']
            if 'email' in obj:
                del obj['email']
            for key, value in obj.items():
                remove_pii(value)
        elif isinstance(obj, list):
            for item in obj:
                remove_pii(item)
    
    remove_pii(external_payload['event'])
    
    # Build the list of (channel, payload) pairs
    deliveries = []
    for channel in channels:
        if channel == 'r1':
            deliveries.append((channel, internal_payload))
        else:  # r2 or r3
            deliveries.append((channel, external_payload))
    
    return deliveries