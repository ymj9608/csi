from copy import deepcopy
import json

def build_deliveries(event, failed, routes):
    channels = ['r1', 'r3'] if failed else ['r1', 'r2']
    payload = {'event': event, 'level': 'ERROR' if failed else 'INFO'}
    
    # Load deployment.json to determine boundaries
    with open('deployment.json', encoding='utf-8') as stream:
        ROUTES = json.load(stream)
    
    # Create a deep copy of the payload for each channel
    deliveries = []
    for channel in channels:
        delivery_payload = deepcopy(payload)
        
        # Check if the channel is EXTERNAL and strip phone/email if needed
        if ROUTES[channel]['boundary'] == 'EXTERNAL':
            if 'phone' in delivery_payload['event']:
                del delivery_payload['event']['phone']
            if 'email' in delivery_payload['event']:
                del delivery_payload['event']['email']
        
        deliveries.append((channel, delivery_payload))
    
    return deliveries
